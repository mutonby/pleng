"""Platform API — orchestrates Docker, domains, state.

The single source of truth. Agent, telegram-bot, and dashboard all talk to this.
"""
import logging
import os
import threading

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

import database as db
import deployer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("platform-api")

app = FastAPI(title="Pleng Platform API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def startup():
    db.init()
    logger.info(f"Platform API ready — PUBLIC_IP={os.environ.get('PUBLIC_IP', '?')}")


# ── Models ──────────────────────────────────────────────

class DeployCompose(BaseModel):
    name: str
    compose_path: str
    env_vars: dict = {}

class DeployGit(BaseModel):
    name: str
    repo_url: str
    branch: str = "main"

class DeployGenerate(BaseModel):
    name: str
    description: str

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


@app.post("/api/deploy/generate")
def api_deploy_generate(body: DeployGenerate):
    """Create workspace for AI agent to generate code, then deploy.

    This just creates the site record and workspace.
    The agent container writes code to /projects/{site_id}/ and then
    calls POST /api/deploy/compose to actually deploy it.
    """
    existing = db.get_site_by_name(body.name)
    if existing:
        raise HTTPException(400, f"Site '{body.name}' already exists")
    site = db.create_site(body.name, deploy_mode="generate", description=body.description)
    workspace = os.path.join(deployer.PROJECTS_DIR, site["id"])
    os.makedirs(workspace, exist_ok=True)
    db.update_site(site["id"], status="generating", project_path=workspace)
    db.add_site_log(site["id"], f"Workspace ready at {workspace}")
    return {
        "site_id": site["id"],
        "name": body.name,
        "status": "generating",
        "workspace": workspace,
    }


# ── Site operations ─────────────────────────────────────

@app.get("/api/sites")
def api_list_sites():
    return db.get_all_sites()


@app.get("/api/sites/{site_id}")
def api_get_site(site_id: str):
    # Allow lookup by id or name
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

## Endpoints

### Deploy from git repo
POST {base}/api/deploy/git
Body: {{"name": "my-app", "repo_url": "https://github.com/user/repo"}}
Returns: {{"site_id": "...", "url": "http://xxxx.{ip}.sslip.io", "status": "staging"}}

### Deploy from docker-compose path (on server)
POST {base}/api/deploy/compose
Body: {{"name": "my-app", "compose_path": "/projects/site_id/docker-compose.yml"}}

### Request AI-generated project
POST {base}/api/deploy/generate
Body: {{"name": "my-app", "description": "A booking API with Postgres"}}
Returns: {{"site_id": "...", "workspace": "/projects/...", "status": "generating"}}
Note: After generating code in the workspace, call deploy/compose to deploy it.

### List all sites
GET {base}/api/sites

### Get site details
GET {base}/api/sites/{{id_or_name}}

### Docker logs
GET {base}/api/sites/{{id}}/logs?lines=100

### Stop / Restart / Remove
POST {base}/api/sites/{{id}}/stop
POST {base}/api/sites/{{id}}/restart
POST {base}/api/sites/{{id}}/remove

### Promote to production (custom domain + SSL)
POST {base}/api/sites/{{id}}/promote
Body: {{"domain": "app.example.com"}}

## How it works
- Every deploy gets a free staging URL: http://{{hash}}.{ip}.sslip.io
- Promote to production with a custom domain to get HTTPS via Let's Encrypt
- All containers are managed via Docker Compose + Traefik
"""


@app.get("/api/health")
def health():
    return {"status": "ok", "sites": len(db.get_all_sites())}
