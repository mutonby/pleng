"""Platform API — orchestrates Docker, domains, state.

The single source of truth. Agent, telegram-bot, and dashboard all talk to this.
Auth: API key auto-generated on first boot. Internal services fetch it via /internal/key.
"""
import ipaddress
import json
import logging
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

import requests as http_requests

import database as db
import deployer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("platform-api")

app = FastAPI(title="Pleng Platform API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_api_key: str = ""

# Docker internal networks (containers talking to each other)
INTERNAL_NETS = [
    ipaddress.ip_network("172.16.0.0/12"),   # Docker default
    ipaddress.ip_network("10.0.0.0/8"),       # Docker overlay
    ipaddress.ip_network("192.168.0.0/16"),   # Docker bridge
    ipaddress.ip_network("127.0.0.0/8"),      # Localhost
]


def _is_internal(ip: str) -> bool:
    """Check if request comes from Docker internal network."""
    try:
        addr = ipaddress.ip_address(ip)
        return any(addr in net for net in INTERNAL_NETS)
    except ValueError:
        return False


_dashboard_password = ""

@app.on_event("startup")
def startup():
    global _api_key, _dashboard_password
    db.init()
    _api_key = db.get_or_create_api_key()

    # Dashboard password: env var > DB > generate random
    env_pass = os.environ.get("WEB_UI_PASSWORD", "")
    if env_pass and env_pass != "admin":
        _dashboard_password = env_pass
    else:
        _dashboard_password = db.get_or_create_password()

    ip = os.environ.get("PUBLIC_IP", "?")
    logger.info("=" * 60)
    logger.info("  Pleng Platform API ready")
    logger.info(f"  PUBLIC_IP:  {ip}")
    logger.info(f"  Panel:      http://panel.{ip}.sslip.io")
    logger.info(f"  API Key:    {_api_key[:16]}...")
    logger.info(f"  Password:   {_dashboard_password}")
    logger.info("=" * 60)

    # Start health monitor
    import monitor
    monitor.start()

    # Start analytics parser (Traefik access logs)
    import analytics
    analytics.start()


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path

    # Public endpoints — no auth
    if path in ("/api/health", "/skill.md", "/api/collect", "/t.js", "/api/auth/login", "/api/setup-status"):
        return await call_next(request)
    if path.startswith("/internal/"):
        return await call_next(request)
    if request.method == "OPTIONS":
        return await call_next(request)

    # Internal network — no auth needed (direct container-to-container)
    # But if X-Forwarded-For is set, it came through Traefik = external
    client_ip = request.client.host if request.client else ""
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    is_proxied = bool(forwarded_for)

    if _is_internal(client_ip) and not is_proxied:
        return await call_next(request)

    # External (or proxied through Traefik) — check API key
    api_key = (
        request.headers.get("X-API-Key", "")
        or request.headers.get("Authorization", "").removeprefix("Bearer ")
        or request.query_params.get("key", "")
    )

    if api_key != _api_key:
        return PlainTextResponse("Unauthorized. Pass API key via X-API-Key header.", status_code=401)

    return await call_next(request)


# ── Internal (container-to-container only) ──────────────

@app.get("/internal/key")
def get_api_key(request: Request):
    """Internal services call this on startup to get the API key.
    Only accessible from Docker internal network."""
    client_ip = request.client.host if request.client else ""
    if not _is_internal(client_ip):
        raise HTTPException(403, "Only accessible from internal network")
    return {"api_key": _api_key}


# ── Internal observability ──────────────────────────────

def _require_internal(request: Request):
    """Raise 403 if request is not from Docker internal network."""
    client_ip = request.client.host if request.client else ""
    if not _is_internal(client_ip):
        raise HTTPException(403, "Only accessible from internal network")


@app.get("/internal/system-stats")
def internal_system_stats(request: Request):
    """System resources: disk, memory, load, uptime."""
    _require_internal(request)

    result = {}

    # Disk usage
    try:
        r = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=5)
        lines = r.stdout.strip().split("\n")
        if len(lines) >= 2:
            parts = lines[1].split()
            result["disk"] = {
                "total": parts[1], "used": parts[2],
                "available": parts[3], "percent": parts[4],
            }
    except Exception:
        result["disk"] = {"error": "unavailable"}

    # Memory (from /proc/meminfo — always available, no procps needed)
    try:
        meminfo = {}
        with open("/proc/meminfo") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    meminfo[parts[0].rstrip(":")] = int(parts[1])  # kB
        total = meminfo.get("MemTotal", 0) // 1024
        available = meminfo.get("MemAvailable", 0) // 1024
        free = meminfo.get("MemFree", 0) // 1024
        used = total - available
        result["memory"] = {
            "total_mb": total, "used_mb": used,
            "free_mb": free, "available_mb": available,
        }
    except Exception:
        result["memory"] = {"error": "unavailable"}

    # Load average
    try:
        with open("/proc/loadavg") as f:
            parts = f.read().split()
            result["load"] = {"1m": float(parts[0]), "5m": float(parts[1]), "15m": float(parts[2])}
    except Exception:
        result["load"] = {"error": "unavailable"}

    # Uptime
    try:
        with open("/proc/uptime") as f:
            secs = float(f.read().split()[0])
            days = int(secs // 86400)
            hours = int((secs % 86400) // 3600)
            result["uptime"] = f"{days}d {hours}h"
    except Exception:
        result["uptime"] = "unavailable"

    return result


@app.get("/internal/docker-ps")
def internal_docker_ps(request: Request):
    """All Docker containers on the host."""
    _require_internal(request)
    try:
        r = subprocess.run(
            ["docker", "ps", "-a", "--format", "{{json .}}"],
            capture_output=True, text=True, timeout=15,
        )
        containers = []
        for line in r.stdout.strip().split("\n"):
            if line.strip():
                containers.append(json.loads(line))
        return containers
    except Exception as e:
        return {"error": str(e)}


@app.get("/internal/docker-stats")
def internal_docker_stats(request: Request):
    """CPU + RAM per running container."""
    _require_internal(request)
    try:
        r = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", "{{json .}}"],
            capture_output=True, text=True, timeout=15,
        )
        stats = []
        for line in r.stdout.strip().split("\n"):
            if line.strip():
                stats.append(json.loads(line))
        return stats
    except Exception as e:
        return {"error": str(e)}


@app.get("/internal/logs-summary")
def internal_logs_summary(request: Request):
    """Recent errors/warnings from all deployed sites."""
    _require_internal(request)
    error_pattern = re.compile(r"(error|exception|traceback|fatal|panic|critical)", re.IGNORECASE)
    summary = {}

    for site in db.get_all_sites():
        if site["status"] not in ("staging", "production"):
            continue
        try:
            logs = deployer.docker_logs(site["id"], lines=50)
            if not logs:
                continue
            errors = [line for line in logs.split("\n") if error_pattern.search(line)]
            if errors:
                summary[site["name"]] = errors[-20:]  # Last 20 error lines max
        except Exception:
            continue

    return summary


@app.get("/internal/traefik-errors")
def internal_traefik_errors(request: Request, minutes: int = 60):
    """5xx errors from Traefik access log in the last N minutes."""
    _require_internal(request)
    log_path = "/var/log/traefik/access.log"
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)

    total = 0
    errors_5xx = 0
    by_domain: dict[str, int] = {}
    recent_errors: list[dict] = []

    try:
        if not os.path.exists(log_path):
            return {"total_requests": 0, "errors_5xx": 0, "error_rate": "0%",
                    "by_domain": {}, "recent_errors": []}

        # Read only the last 2MB of the file to avoid loading huge logs into memory
        with open(log_path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 2 * 1024 * 1024))
            if f.tell() > 0:
                f.readline()  # Skip partial first line
            content = f.read().decode("utf-8", errors="replace")
        lines = content.split("\n")

        for line in lines:
            try:
                entry = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue

            # Parse timestamp
            ts_str = entry.get("time", "")
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                continue

            if ts < cutoff:
                continue

            total += 1
            status = int(entry.get("DownstreamStatus", entry.get("status", 0)))

            if status >= 500:
                errors_5xx += 1
                domain = entry.get("RequestHost", entry.get("request", {}).get("host", "unknown"))
                by_domain[domain] = by_domain.get(domain, 0) + 1
                recent_errors.append({
                    "time": ts_str,
                    "domain": domain,
                    "path": entry.get("RequestPath", entry.get("request", {}).get("path", "")),
                    "status": status,
                })

    except Exception as e:
        return {"error": str(e)}

    error_rate = f"{(errors_5xx / total * 100):.1f}%" if total > 0 else "0%"
    return {
        "total_requests": total,
        "errors_5xx": errors_5xx,
        "error_rate": error_rate,
        "by_domain": by_domain,
        "recent_errors": recent_errors[-50:],  # Last 50 errors max
    }


# ── Auth ─────────────────────────────────────────────────

class LoginRequest(BaseModel):
    password: str

@app.post("/api/auth/login")
def login(body: LoginRequest):
    """Dashboard login. Returns API key if password matches."""
    if body.password != _dashboard_password:
        raise HTTPException(401, "Wrong password")
    return {"api_key": _api_key}


# ── Models ──────────────────────────────────────────────

class DeployCompose(BaseModel):
    name: str
    compose_path: str
    env_vars: dict = {}

class DeployGit(BaseModel):
    name: str
    repo_url: str
    branch: str = "main"

class PromoteSite(BaseModel):
    domain: str

class PushGit(BaseModel):
    repo: str  # e.g. "mutonby/pleng-site"
    message: str = "Deploy from Pleng"


# ── Deploy endpoints ────────────────────────────────────

@app.post("/api/deploy/compose")
def api_deploy_compose(body: DeployCompose):
    existing = db.get_site_by_name(body.name)
    if existing:
        raise HTTPException(400, f"Site '{body.name}' already exists")

    # Resolve compose_path: if it doesn't exist, try PROJECTS_DIR/name
    compose_path = body.compose_path
    if not os.path.exists(compose_path):
        fallback = os.path.join(deployer.PROJECTS_DIR, body.name)
        if os.path.exists(fallback):
            compose_path = fallback
        else:
            raise HTTPException(400, f"Path not found: {compose_path} (also tried {fallback})")

    site = db.create_site(body.name, deploy_mode="compose")
    try:
        result = deployer.deploy_compose(site["id"], body.name, compose_path)
        return result
    except Exception as e:
        db.update_site(site["id"], status="error")
        db.add_site_log(site["id"], str(e), level="error")
        raise HTTPException(500, str(e))


@app.post("/api/deploy/git")
def api_deploy_git(body: DeployGit):
    existing = db.get_site_by_name(body.name)
    if existing:
        raise HTTPException(400, f"Site '{body.name}' already exists")
    site = db.create_site(body.name, deploy_mode="git", github_url=body.repo_url)
    try:
        result = deployer.deploy_git(site["id"], body.name, body.repo_url, body.branch)
        return result
    except Exception as e:
        db.update_site(site["id"], status="error")
        db.add_site_log(site["id"], str(e), level="error")
        raise HTTPException(500, str(e))


@app.post("/api/deploy/upload")
async def api_deploy_upload(name: str = Form(...), file: UploadFile = File(...)):
    """Upload a tar.gz of a project and deploy it.

    For external agents (Claude Code on your Mac, etc.) to deploy without git.
    tar -czf project.tar.gz -C /path/to/project .
    """
    existing = db.get_site_by_name(name)
    if existing:
        raise HTTPException(400, f"Site '{name}' already exists")

    site = db.create_site(name, deploy_mode="upload")

    try:
        workspace = os.path.join(deployer.PROJECTS_DIR, site["id"])
        os.makedirs(workspace, exist_ok=True)

        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        with tarfile.open(tmp_path, "r:gz") as tar:
            tar.extractall(workspace, filter="data")
        os.unlink(tmp_path)

        db.add_site_log(site["id"], f"Uploaded and extracted ({len(content)} bytes)")

        # Check for docker-compose.yml (might be nested one level deep from tar)
        compose_file = os.path.join(workspace, "docker-compose.yml")
        if not os.path.exists(compose_file):
            for item in os.listdir(workspace):
                sub = os.path.join(workspace, item, "docker-compose.yml")
                if os.path.exists(sub):
                    src_dir = os.path.join(workspace, item)
                    for f_name in os.listdir(src_dir):
                        shutil.move(os.path.join(src_dir, f_name), os.path.join(workspace, f_name))
                    os.rmdir(src_dir)
                    break

        result = deployer.deploy_compose(site["id"], name, workspace)
        return result

    except Exception as e:
        db.update_site(site["id"], status="error")
        db.add_site_log(site["id"], str(e), level="error")
        raise HTTPException(500, str(e))


# ── Site operations ─────────────────────────────────────

@app.get("/api/sites")
def api_list_sites():
    return db.get_all_sites()


@app.get("/api/sites/{site_id}")
def api_get_site(site_id: str):
    site = db.get_site(site_id) or db.get_site_by_name(site_id)
    if not site:
        raise HTTPException(404, "Site not found")
    return site


@app.post("/api/sites/{site_id}/redeploy")
def api_redeploy(site_id: str):
    """Rebuild and restart a site."""
    site = db.get_site(site_id) or db.get_site_by_name(site_id)
    if not site:
        raise HTTPException(404)
    result = deployer.redeploy(site["id"])
    if "error" in result:
        raise HTTPException(500, result["error"])
    return result


@app.post("/api/sites/{site_id}/stop")
def api_stop(site_id: str):
    site = db.get_site(site_id) or db.get_site_by_name(site_id)
    if not site:
        raise HTTPException(404)
    return {"ok": deployer.stop(site["id"])}


@app.post("/api/sites/{site_id}/restart")
def api_restart(site_id: str):
    site = db.get_site(site_id) or db.get_site_by_name(site_id)
    if not site:
        raise HTTPException(404)
    return {"ok": deployer.restart(site["id"])}


@app.post("/api/sites/{site_id}/remove")
def api_remove(site_id: str):
    """Remove a site. Production keeps files. Staging deletes everything."""
    site = db.get_site(site_id) or db.get_site_by_name(site_id)
    if not site:
        raise HTTPException(404)
    return {"ok": deployer.remove(site["id"]), "kept_files": site.get("status") == "production"}


@app.post("/api/sites/{site_id}/destroy")
def api_destroy(site_id: str):
    """Permanently destroy — containers + files + DB. No undo."""
    site = db.get_site(site_id) or db.get_site_by_name(site_id)
    if not site:
        raise HTTPException(404)
    return {"ok": deployer.destroy(site["id"])}


@app.get("/api/sites/{site_id}/logs")
def api_logs(site_id: str, lines: int = 100):
    site = db.get_site(site_id) or db.get_site_by_name(site_id)
    if not site:
        raise HTTPException(404)
    return {"logs": deployer.docker_logs(site["id"], lines)}


@app.get("/api/sites/{site_id}/containers")
def api_containers(site_id: str):
    site = db.get_site(site_id) or db.get_site_by_name(site_id)
    if not site:
        raise HTTPException(404)
    return deployer.container_status(site["id"])


@app.get("/api/sites/{site_id}/analytics")
def api_site_analytics(site_id: str, period: str = "7d"):
    """Traffic analytics for a site (from Traefik access logs)."""
    site = db.get_site(site_id) or db.get_site_by_name(site_id)
    if not site:
        raise HTTPException(404)
    domain = site.get("production_domain") or site.get("staging_domain") or ""
    if not domain:
        return {"stats": {}, "top_pages": [], "top_sources": [], "daily": []}
    import analytics
    return {
        "stats": analytics.get_site_stats(domain, period),
        "top_pages": analytics.get_top_pages(domain, period),
        "top_sources": analytics.get_top_sources(domain, period),
        "daily": analytics.get_daily_stats(domain, period),
    }


@app.get("/api/sites/{site_id}/build-logs")
def api_build_logs(site_id: str):
    site = db.get_site(site_id) or db.get_site_by_name(site_id)
    if not site:
        raise HTTPException(404)
    return db.get_site_logs(site["id"])


@app.post("/api/sites/{site_id}/promote")
def api_promote(site_id: str, body: PromoteSite):
    site = db.get_site(site_id) or db.get_site_by_name(site_id)
    if not site:
        raise HTTPException(404)
    try:
        return deployer.promote(site["id"], body.domain)
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/sites/{site_id}/push-git")
def api_push_git(site_id: str, body: PushGit):
    """Push a site's code to a GitHub repo."""
    site = db.get_site(site_id) or db.get_site_by_name(site_id)
    if not site:
        raise HTTPException(404)
    workspace = deployer._resolve_workspace(site)
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise HTTPException(400, "GITHUB_TOKEN not configured")

    try:
        repo = body.repo
        parts = repo.split("/")
        if len(parts) == 2:
            org, name = parts
        else:
            raise HTTPException(400, "repo must be 'owner/name'")

        clone_url = f"https://x-access-token:{token}@github.com/{repo}.git"

        # Create repo if it doesn't exist
        headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
        resp = http_requests.post(
            f"https://api.github.com/orgs/{org}/repos",
            headers=headers,
            json={"name": name, "private": True, "auto_init": False},
            timeout=15,
        )
        if resp.status_code == 404:
            http_requests.post(
                "https://api.github.com/user/repos",
                headers=headers,
                json={"name": name, "private": True, "auto_init": False},
                timeout=15,
            )

        # Git init + add + commit + push
        env = os.environ.copy()
        env["GIT_AUTHOR_NAME"] = "Pleng"
        env["GIT_AUTHOR_EMAIL"] = "pleng@automated.dev"
        env["GIT_COMMITTER_NAME"] = "Pleng"
        env["GIT_COMMITTER_EMAIL"] = "pleng@automated.dev"

        def _git(*args):
            r = subprocess.run(["git"] + list(args), cwd=workspace, capture_output=True, text=True, env=env, timeout=60)
            if r.returncode != 0 and "already exists" not in r.stderr:
                logger.error(f"git {' '.join(args)} failed: {r.stderr[:300]}")
            return r

        # Fix ownership issue (agent creates files as uid 1000, platform-api runs as root)
        _git("config", "--global", "--add", "safe.directory", workspace)

        # Init if needed
        if not os.path.exists(os.path.join(workspace, ".git")):
            _git("init")
            _git("branch", "-M", "main")

        # Set remote
        _git("remote", "remove", "origin")
        _git("remote", "add", "origin", clone_url)

        # Add, commit, push
        _git("add", "-A")
        commit_result = _git("commit", "-m", body.message, "--allow-empty")
        push_result = _git("push", "-u", "origin", "main")

        if push_result.returncode != 0:
            error = push_result.stderr[:300]
            raise RuntimeError(f"git push failed: {error}")

        repo_url = f"https://github.com/{repo}"
        db.update_site(site["id"], github_url=repo_url)
        db.add_site_log(site["id"], f"Pushed to {repo_url}")

        return {"ok": True, "repo": repo_url}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/sites/{site_id}/pull-git")
def api_pull_git(site_id: str):
    """Pull latest code from GitHub and redeploy."""
    site = db.get_site(site_id) or db.get_site_by_name(site_id)
    if not site:
        raise HTTPException(404)
    workspace = deployer._resolve_workspace(site)
    github_url = site.get("github_url", "")
    if not github_url:
        raise HTTPException(400, "No GitHub repo linked. Push first with push-git.")

    token = os.environ.get("GITHUB_TOKEN", "")
    clone_url = github_url.replace("https://github.com/", f"https://x-access-token:{token}@github.com/") + ".git"

    try:
        # Set remote URL with token
        subprocess.run(["git", "remote", "set-url", "origin", clone_url],
                       cwd=workspace, capture_output=True, text=True, timeout=10)

        # Pull
        r = subprocess.run(["git", "pull", "origin", "main"],
                           cwd=workspace, capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            raise RuntimeError(f"git pull failed: {r.stderr[:200]}")

        db.add_site_log(site["id"], "Pulled from GitHub")

        # Redeploy
        result = deployer.redeploy(site["id"])
        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Skill.md ────────────────────────────────────────────

@app.get("/skill.md", response_class=PlainTextResponse)
def skill_md():
    ip = os.environ.get("PUBLIC_IP", "127.0.0.1")
    base = f"http://panel.{ip}.sslip.io"
    return f"""# Pleng — Your AI Platform Engineer

This is a Pleng instance. You can use this API to deploy and manage web applications on this server.

## Quick start

To deploy a project from a git repo:
```bash
curl -X POST {base}/api/deploy/git \\
  -H "X-API-Key: YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{{"name": "my-app", "repo_url": "https://github.com/user/repo"}}'
```

The response includes a staging URL like `http://xxxx.{ip}.sslip.io` where the app is immediately accessible.

## Authentication

Every request needs an API key in the header:
```
X-API-Key: YOUR_API_KEY
```

## Endpoints

### Deploy

**From git repo** (the repo must contain a docker-compose.yml or Dockerfile):
```
POST {base}/api/deploy/git
Body: {{"name": "my-app", "repo_url": "https://github.com/user/repo"}}
Response: {{"site_id": "...", "status": "staging", "url": "http://xxxx.{ip}.sslip.io"}}
```

**By uploading a tar.gz** (must contain docker-compose.yml or Dockerfile):
```
POST {base}/api/deploy/upload
Content-Type: multipart/form-data
Fields: name=my-app, file=@project.tar.gz
```
Create the tarball: `tar -czf project.tar.gz -C /path/to/project .`

### Manage sites

```
GET  {base}/api/sites                        List all sites
GET  {base}/api/sites/{{name_or_id}}           Get site details
GET  {base}/api/sites/{{name_or_id}}/logs      Docker logs (?lines=100)
GET  {base}/api/sites/{{name_or_id}}/containers Container status
POST {base}/api/sites/{{name_or_id}}/redeploy  Rebuild and restart
POST {base}/api/sites/{{name_or_id}}/stop      Stop containers
POST {base}/api/sites/{{name_or_id}}/restart   Restart containers
POST {base}/api/sites/{{name_or_id}}/remove    Remove site
```

### Promote to production

When a staging site is ready, give it a custom domain with automatic HTTPS:
```
POST {base}/api/sites/{{name_or_id}}/promote
Body: {{"domain": "app.example.com"}}
```

## How it works

1. Every deploy starts as **staging** with a free URL: `http://{{hash}}.{ip}.sslip.io`
2. No domain needed. No DNS config. Works instantly.
3. Promote to production → custom domain + HTTPS via Let's Encrypt.
4. The user's docker-compose.yml is never modified. Pleng generates its own overlay.

## Example: deploy, check, promote

```bash
API="{base}"
KEY="YOUR_API_KEY"

# Deploy
curl -s -X POST $API/api/deploy/git \\
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \\
  -d '{{"name": "my-app", "repo_url": "https://github.com/user/repo"}}'

# Check status
curl -s -H "X-API-Key: $KEY" $API/api/sites/my-app

# View logs
curl -s -H "X-API-Key: $KEY" $API/api/sites/my-app/logs

# Promote to production
curl -s -X POST $API/api/sites/my-app/promote \\
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \\
  -d '{{"domain": "app.mydomain.com"}}'
```
"""


@app.get("/api/health")
def health():
    return {"status": "ok", "sites": len(db.get_all_sites())}


@app.get("/api/setup-status")
def setup_status():
    """What's configured and what's missing. Used by dashboard onboarding."""
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    telegram_chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    ip = os.environ.get("PUBLIC_IP", "")

    # Get bot username (cached)
    bot_username = ""
    if telegram_token:
        if not hasattr(setup_status, "_bot"):
            try:
                r = http_requests.get(f"https://api.telegram.org/bot{telegram_token}/getMe", timeout=5)
                if r.status_code == 200:
                    setup_status._bot = r.json().get("result", {}).get("username", "")
            except Exception:
                setup_status._bot = ""
        bot_username = getattr(setup_status, "_bot", "")

    sites = db.get_all_sites()

    return {
        "telegram_configured": bool(telegram_token and telegram_chat),
        "telegram_bot": bot_username,
        "public_ip": ip,
        "sites_count": len(sites),
        "panel_url": f"http://panel.{ip}.sslip.io" if ip else "",
    }
