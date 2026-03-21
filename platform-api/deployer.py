"""Docker deploy engine. Manages containers via docker compose CLI.

Every project lives in /projects/{site_id}/ with its own docker-compose.yml.
Traefik labels are injected for automatic routing + SSL.
"""
import hashlib
import logging
import os
import shutil
import subprocess

import yaml

import database as db

logger = logging.getLogger(__name__)

PROJECTS_DIR = os.environ.get("PROJECTS_DIR", "/projects")
PUBLIC_IP = os.environ.get("PUBLIC_IP", "127.0.0.1")
BASE_DOMAIN = os.environ.get("BASE_DOMAIN", "")
NETWORK = "pleng_web"


def staging_domain(name: str) -> str:
    """Generate sslip.io staging domain: {hash}.{IP}.sslip.io"""
    h = hashlib.md5(name.encode()).hexdigest()[:4]
    return f"{h}.{PUBLIC_IP}.sslip.io"


def deploy_compose(site_id: str, name: str, compose_source: str) -> dict:
    """Deploy from an existing docker-compose.yml path or directory."""
    workspace = _prepare_workspace(site_id)

    if os.path.isfile(compose_source):
        shutil.copy2(compose_source, os.path.join(workspace, "docker-compose.yml"))
    elif os.path.isdir(compose_source):
        for item in os.listdir(compose_source):
            src = os.path.join(compose_source, item)
            dst = os.path.join(workspace, item)
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
    else:
        raise FileNotFoundError(f"Source not found: {compose_source}")

    return _deploy(site_id, name, workspace)


def deploy_git(site_id: str, name: str, repo_url: str, branch: str = "main") -> dict:
    """Clone a git repo and deploy it."""
    workspace = _prepare_workspace(site_id)

    token = os.environ.get("GITHUB_TOKEN", "")
    clone_url = repo_url
    if token and "github.com" in repo_url:
        clone_url = repo_url.replace("https://github.com/", f"https://x-access-token:{token}@github.com/")

    result = subprocess.run(
        ["git", "clone", "--depth", "1", "-b", branch, clone_url, workspace],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git clone failed: {result.stderr[:300]}")

    db.add_site_log(site_id, f"Cloned {repo_url}")
    db.update_site(site_id, github_url=repo_url)

    compose_file = os.path.join(workspace, "docker-compose.yml")
    if not os.path.exists(compose_file):
        generated = _auto_generate_compose(workspace)
        if generated:
            with open(compose_file, "w") as f:
                f.write(generated)
            db.add_site_log(site_id, "Auto-generated docker-compose.yml")
        else:
            raise FileNotFoundError("No docker-compose.yml and could not auto-detect project type")

    return _deploy(site_id, name, workspace)


def stop(site_id: str) -> bool:
    site = db.get_site(site_id)
    if not site:
        return False
    project = f"pleng-{site['name']}"
    workspace = os.path.join(PROJECTS_DIR, site_id)
    r = subprocess.run(["docker", "compose", "-p", project, "stop"],
                       cwd=workspace, capture_output=True, text=True, timeout=60)
    if r.returncode == 0:
        db.update_site(site_id, status="stopped")
        db.add_site_log(site_id, "Stopped")
        return True
    return False


def restart(site_id: str) -> bool:
    site = db.get_site(site_id)
    if not site:
        return False
    project = f"pleng-{site['name']}"
    workspace = os.path.join(PROJECTS_DIR, site_id)
    r = subprocess.run(["docker", "compose", "-p", project, "restart"],
                       cwd=workspace, capture_output=True, text=True, timeout=60)
    if r.returncode == 0:
        db.update_site(site_id, status="staging" if not site.get("production_domain") else "production")
        db.add_site_log(site_id, "Restarted")
        return True
    return False


def remove(site_id: str) -> bool:
    site = db.get_site(site_id)
    if not site:
        return False
    project = f"pleng-{site['name']}"
    workspace = os.path.join(PROJECTS_DIR, site_id)
    subprocess.run(["docker", "compose", "-p", project, "down", "-v", "--remove-orphans"],
                   cwd=workspace, capture_output=True, text=True, timeout=60)
    db.delete_site(site_id)
    if os.path.exists(workspace):
        shutil.rmtree(workspace, ignore_errors=True)
    return True


def docker_logs(site_id: str, lines: int = 100) -> str:
    site = db.get_site(site_id)
    if not site:
        return "Site not found"
    project = f"pleng-{site['name']}"
    workspace = os.path.join(PROJECTS_DIR, site_id)
    r = subprocess.run(["docker", "compose", "-p", project, "logs", "--tail", str(lines)],
                       cwd=workspace, capture_output=True, text=True, timeout=30)
    return r.stdout or r.stderr or "No logs"


def container_status(site_id: str) -> list[dict]:
    site = db.get_site(site_id)
    if not site:
        return []
    project = f"pleng-{site['name']}"
    workspace = os.path.join(PROJECTS_DIR, site_id)
    r = subprocess.run(["docker", "compose", "-p", project, "ps", "--format", "json"],
                       cwd=workspace, capture_output=True, text=True, timeout=15)
    import json
    containers = []
    for line in (r.stdout or "").strip().split("\n"):
        if line.strip():
            try:
                containers.append(json.loads(line))
            except Exception:
                pass
    return containers


def promote(site_id: str, domain: str) -> dict:
    """Promote a staging site to production with a custom domain + SSL."""
    site = db.get_site(site_id)
    if not site:
        raise ValueError("Site not found")

    workspace = os.path.join(PROJECTS_DIR, site_id)
    compose_file = os.path.join(workspace, "docker-compose.yml")

    with open(compose_file) as f:
        compose = yaml.safe_load(f)

    # Find the main service and add production Traefik labels
    main_svc = _find_main_service(compose)
    labels = compose["services"][main_svc].get("labels", [])
    if isinstance(labels, dict):
        labels = [f"{k}={v}" for k, v in labels.items()]

    router = site["name"].replace("-", "").replace("_", "")
    prod_labels = [
        f"traefik.http.routers.{router}-prod.rule=Host(`{domain}`)",
        f"traefik.http.routers.{router}-prod.entrypoints=websecure",
        f"traefik.http.routers.{router}-prod.tls.certresolver=letsencrypt",
    ]

    existing_keys = {l.split("=")[0] for l in labels if "=" in l}
    for l in prod_labels:
        if l.split("=")[0] not in existing_keys:
            labels.append(l)

    compose["services"][main_svc]["labels"] = labels

    with open(compose_file, "w") as f:
        yaml.dump(compose, f, default_flow_style=False, sort_keys=False)

    # Recreate to pick up new labels
    project = f"pleng-{site['name']}"
    subprocess.run(["docker", "compose", "-p", project, "up", "-d"],
                   cwd=workspace, capture_output=True, text=True, timeout=120)

    db.update_site(site_id, production_domain=domain, status="production")
    db.add_site_log(site_id, f"Promoted to production: {domain}")

    return {
        "site_id": site_id,
        "domain": domain,
        "url": f"https://{domain}",
        "status": "production",
    }


# ── Internal ────────────────────────────────────────────

def _prepare_workspace(site_id: str) -> str:
    workspace = os.path.join(PROJECTS_DIR, site_id)
    os.makedirs(workspace, exist_ok=True)
    return workspace


def _deploy(site_id: str, name: str, workspace: str) -> dict:
    compose_file = os.path.join(workspace, "docker-compose.yml")
    if not os.path.exists(compose_file):
        raise FileNotFoundError("No docker-compose.yml in workspace")

    domain = staging_domain(name)
    _inject_traefik_labels(compose_file, name, domain)

    db.add_site_log(site_id, "Building and starting containers...")
    project = f"pleng-{name}"

    result = subprocess.run(
        ["docker", "compose", "-p", project, "up", "-d", "--build"],
        cwd=workspace, capture_output=True, text=True, timeout=300,
    )

    if result.returncode != 0:
        error = result.stderr[:500]
        db.update_site(site_id, status="error")
        db.add_site_log(site_id, f"Deploy failed: {error}", level="error")
        return {"site_id": site_id, "name": name, "status": "error", "error": error}

    _connect_network(project)

    from datetime import datetime
    url = f"http://{domain}"
    db.update_site(
        site_id,
        status="staging",
        staging_domain=domain,
        project_path=workspace,
        deployed_at=datetime.utcnow().isoformat(),
    )
    db.add_site_log(site_id, f"Live at {url}")

    return {"site_id": site_id, "name": name, "status": "staging", "url": url, "domain": domain}


def _inject_traefik_labels(compose_file: str, name: str, domain: str):
    try:
        with open(compose_file) as f:
            compose = yaml.safe_load(f)

        if not compose or "services" not in compose:
            return

        main_svc = _find_main_service(compose)
        svc = compose["services"][main_svc]

        # Detect internal port
        ports = svc.get("ports", [])
        internal_port = "80"
        if ports:
            p = str(ports[0])
            internal_port = p.split(":")[-1] if ":" in p else p

        # Remove host port bindings (Traefik handles routing)
        svc.pop("ports", None)

        router = name.replace("-", "").replace("_", "").replace(".", "")
        labels = svc.get("labels", [])
        if isinstance(labels, dict):
            labels = [f"{k}={v}" for k, v in labels.items()]

        traefik_labels = [
            "traefik.enable=true",
            f"traefik.http.routers.{router}.rule=Host(`{domain}`)",
            f"traefik.http.routers.{router}.entrypoints=web",
            f"traefik.http.services.{router}.loadbalancer.server.port={internal_port}",
        ]

        existing = {l.split("=")[0] for l in labels if "=" in l}
        for l in traefik_labels:
            if l.split("=")[0] not in existing:
                labels.append(l)

        svc["labels"] = labels

        # Network
        networks = svc.get("networks", [])
        if isinstance(networks, list) and "pleng_web" not in networks:
            networks.append("pleng_web")
        elif isinstance(networks, dict) and "pleng_web" not in networks:
            networks["pleng_web"] = {}
        svc["networks"] = networks

        if "networks" not in compose:
            compose["networks"] = {}
        compose["networks"]["pleng_web"] = {"external": True}

        with open(compose_file, "w") as f:
            yaml.dump(compose, f, default_flow_style=False, sort_keys=False)

    except Exception as e:
        logger.warning(f"Failed to inject Traefik labels: {e}")


def _find_main_service(compose: dict) -> str:
    for name, cfg in compose.get("services", {}).items():
        if cfg.get("ports"):
            return name
    return list(compose.get("services", {}).keys())[0]


def _connect_network(project: str):
    try:
        r = subprocess.run(["docker", "compose", "-p", project, "ps", "-q"],
                           capture_output=True, text=True, timeout=10)
        for cid in r.stdout.strip().split("\n"):
            if cid.strip():
                subprocess.run(["docker", "network", "connect", NETWORK, cid.strip()],
                               capture_output=True, text=True, timeout=10)
    except Exception as e:
        logger.warning(f"Network connect: {e}")


def _auto_generate_compose(workspace: str) -> str | None:
    if os.path.exists(os.path.join(workspace, "Dockerfile")):
        return "services:\n  web:\n    build: .\n    ports:\n      - '80:80'\n    restart: unless-stopped\n"
    if os.path.exists(os.path.join(workspace, "package.json")):
        return "services:\n  web:\n    build: .\n    ports:\n      - '80:3000'\n    restart: unless-stopped\n"
    if os.path.exists(os.path.join(workspace, "requirements.txt")):
        return "services:\n  web:\n    build: .\n    ports:\n      - '80:8000'\n    restart: unless-stopped\n"
    return None
