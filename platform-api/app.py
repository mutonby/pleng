"""Platform API — orchestrates Docker, domains, state.

The single source of truth. Agent, telegram-bot, and dashboard all talk to this.
Auth: API key auto-generated on first boot. Internal services fetch it via /internal/key.
"""
import ipaddress
import logging
import os
import shutil
import tarfile
import tempfile

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

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


@app.on_event("startup")
def startup():
    global _api_key
    db.init()
    _api_key = db.get_or_create_api_key()
    ip = os.environ.get("PUBLIC_IP", "?")
    logger.info("=" * 60)
    logger.info("  Pleng Platform API ready")
    logger.info(f"  PUBLIC_IP: {ip}")
    logger.info(f"  Panel:     http://panel.{ip}.sslip.io")
    logger.info(f"  API Key:   {_api_key}")
    logger.info("=" * 60)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path

    # Public endpoints — no auth
    if path in ("/api/health", "/skill.md", "/api/collect", "/t.js", "/api/auth/login"):
        return await call_next(request)
    if path == "/internal/key":
        return await call_next(request)
    if request.method == "OPTIONS":
        return await call_next(request)

    # Internal network — no auth needed (container-to-container)
    client_ip = request.client.host if request.client else ""
    if _is_internal(client_ip):
        return await call_next(request)

    # External — check API key
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


# ── Auth ─────────────────────────────────────────────────

class LoginRequest(BaseModel):
    password: str

@app.post("/api/auth/login")
def login(body: LoginRequest):
    """Dashboard login. Returns API key if password matches."""
    expected = os.environ.get("WEB_UI_PASSWORD", "admin")
    if body.password != expected:
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


# ── Deploy endpoints ────────────────────────────────────

@app.post("/api/deploy/compose")
def api_deploy_compose(body: DeployCompose):
    existing = db.get_site_by_name(body.name)
    if existing:
        raise HTTPException(400, f"Site '{body.name}' already exists")
    site = db.create_site(body.name, deploy_mode="compose")
    try:
        result = deployer.deploy_compose(site["id"], body.name, body.compose_path)
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
    site = db.get_site(site_id) or db.get_site_by_name(site_id)
    if not site:
        raise HTTPException(404)
    return {"ok": deployer.remove(site["id"])}


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


# ── Skill.md ────────────────────────────────────────────

@app.get("/skill.md", response_class=PlainTextResponse)
def skill_md():
    ip = os.environ.get("PUBLIC_IP", "127.0.0.1")
    base = f"http://panel.{ip}.sslip.io"
    return f"""# Pleng — AI PaaS Skill

Connect to this Pleng instance to deploy and manage web applications.

## Base URL
{base}

## Authentication
All requests need an API key. Pass it as a header:
```
X-API-Key: <your-api-key>
```
Get your API key from `docker compose logs platform-api` or from the dashboard.

## Deploy from git repo
```
POST {base}/api/deploy/git
X-API-Key: <key>
Body: {{"name": "my-app", "repo_url": "https://github.com/user/repo"}}
```

## Deploy by uploading code (tar.gz)
```
POST {base}/api/deploy/upload
X-API-Key: <key>
Content-Type: multipart/form-data
Fields: name=my-app, file=@project.tar.gz
```
To create the tarball: `tar -czf project.tar.gz -C /path/to/project .`
The project MUST contain a docker-compose.yml (or at least a Dockerfile).

## List all sites
```
GET {base}/api/sites
X-API-Key: <key>
```

## Get site details
```
GET {base}/api/sites/{{id_or_name}}
```

## Docker logs
```
GET {base}/api/sites/{{id}}/logs?lines=100
```

## Stop / Restart / Remove
```
POST {base}/api/sites/{{id}}/stop
POST {base}/api/sites/{{id}}/restart
POST {base}/api/sites/{{id}}/remove
```

## Promote staging → production (custom domain + HTTPS)
```
POST {base}/api/sites/{{id}}/promote
Body: {{"domain": "app.example.com"}}
```

## How it works
1. Every deploy starts as **staging** with a free URL: `http://{{hash}}.{ip}.sslip.io`
2. No domain needed. No DNS config. Works instantly.
3. When ready, **promote** to production with a custom domain → automatic HTTPS via Let's Encrypt.
4. Stop, restart, or remove anytime.
"""


@app.get("/api/health")
def health():
    return {"status": "ok", "sites": len(db.get_all_sites())}
