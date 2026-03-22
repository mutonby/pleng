"""Docker deploy engine. Manages containers via docker compose CLI.

Every project lives in /projects/{site_id}/ with its own docker-compose.yml.
Traefik labels are injected for automatic routing + SSL.
"""
import hashlib
import json
import logging
import os
import shutil
import subprocess
from datetime import datetime

import yaml

import database as db

logger = logging.getLogger(__name__)

PROJECTS_DIR = os.environ.get("PROJECTS_DIR", "/opt/pleng/projects")
PUBLIC_IP = os.environ.get("PUBLIC_IP", "127.0.0.1")
BASE_DOMAIN = os.environ.get("BASE_DOMAIN", "")
NETWORK = "pleng_web"


def staging_domain(name: str) -> str:
    """Generate sslip.io staging domain: {hash}.{IP}.sslip.io"""
    h = hashlib.md5(name.encode()).hexdigest()[:4]
    return f"{h}.{PUBLIC_IP}.sslip.io"


def deploy_compose(site_id: str, name: str, compose_source: str) -> dict:
    """Deploy from an existing docker-compose.yml path or directory."""
    # If source is a directory with a docker-compose.yml, use it directly as workspace
    if os.path.isdir(compose_source) and os.path.exists(os.path.join(compose_source, "docker-compose.yml")):
        workspace = compose_source
        db.update_site(site_id, project_path=workspace)
    elif os.path.isfile(compose_source):
        workspace = _prepare_workspace(site_id)
        shutil.copy2(compose_source, os.path.join(workspace, "docker-compose.yml"))
    else:
        raise FileNotFoundError(f"Source not found or no docker-compose.yml: {compose_source}")

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
    workspace = site.get("project_path") or os.path.join(PROJECTS_DIR, site_id)
    r = subprocess.run(_compose_cmd(project, workspace, "stop"),
                       capture_output=True, text=True, timeout=60)
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
    workspace = site.get("project_path") or os.path.join(PROJECTS_DIR, site_id)
    r = subprocess.run(_compose_cmd(project, workspace, "restart"),
                       capture_output=True, text=True, timeout=60)
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
    workspace = site.get("project_path") or os.path.join(PROJECTS_DIR, site_id)
    subprocess.run(_compose_cmd(project, workspace, "down", "-v", "--remove-orphans"),
                   capture_output=True, text=True, timeout=60)
    db.delete_site(site_id)
    if os.path.exists(workspace):
        shutil.rmtree(workspace, ignore_errors=True)
    return True


def docker_logs(site_id: str, lines: int = 100) -> str:
    site = db.get_site(site_id)
    if not site:
        return "Site not found"
    project = f"pleng-{site['name']}"
    workspace = site.get("project_path") or os.path.join(PROJECTS_DIR, site_id)
    r = subprocess.run(_compose_cmd(project, workspace, "logs", "--tail", str(lines)),
                       capture_output=True, text=True, timeout=30)
    return r.stdout or r.stderr or "No logs"


def container_status(site_id: str) -> list[dict]:
    site = db.get_site(site_id)
    if not site:
        return []
    project = f"pleng-{site['name']}"
    workspace = site.get("project_path") or os.path.join(PROJECTS_DIR, site_id)
    r = subprocess.run(_compose_cmd(project, workspace, "ps", "--format", "json"),
                       capture_output=True, text=True, timeout=15)
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

    router = site["name"].replace("-", "").replace("_", "").replace(".", "")

    # Find the existing service name from staging labels
    svc_label_key = f"traefik.http.services.{router}.loadbalancer.server.port"
    internal_port = "80"
    for l in labels:
        if svc_label_key in l:
            internal_port = l.split("=")[-1]
            break

    prod_labels = [
        f"traefik.http.routers.{router}-prod.rule=Host(`{domain}`)",
        f"traefik.http.routers.{router}-prod.entrypoints=websecure",
        f"traefik.http.routers.{router}-prod.tls.certresolver=letsencrypt",
        f"traefik.http.routers.{router}-prod.service={router}",
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
    result = subprocess.run(_compose_cmd(project, workspace, "up", "-d"),
                            capture_output=True, text=True, timeout=120)

    if result.returncode != 0:
        error = result.stderr[:300]
        db.add_site_log(site_id, f"Promote failed: {error}", level="error")
        raise RuntimeError(f"Promote deploy failed: {error}")

    db.update_site(site_id, production_domain=domain, status="production")
    db.add_site_log(site_id, f"Promoted to production: https://{domain}")

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


def _compose_cmd(project: str, workspace: str, *args) -> list[str]:
    """Build a docker compose command. Uses container path (CLI reads file locally)."""
    compose_file = os.path.join(workspace, "docker-compose.yml")
    return ["docker", "compose", "-f", compose_file, "-p", project] + list(args)


def _deploy(site_id: str, name: str, workspace: str) -> dict:
    compose_file = os.path.join(workspace, "docker-compose.yml")
    if not os.path.exists(compose_file):
        raise FileNotFoundError("No docker-compose.yml in workspace")

    domain = staging_domain(name)
    _inject_traefik_labels(compose_file, name, domain)

    # Rewrite build contexts to use host paths (Docker daemon runs on host, not in container)
    _rewrite_build_contexts(compose_file, workspace)

    db.add_site_log(site_id, "Building and starting containers...")
    project = f"pleng-{name}"

    result = subprocess.run(
        _compose_cmd(project, workspace, "up", "-d", "--build"),
        capture_output=True, text=True, timeout=300,
    )

    if result.returncode != 0:
        error = result.stderr[:500]
        db.update_site(site_id, status="error")
        db.add_site_log(site_id, f"Deploy failed: {error}", level="error")
        return {"site_id": site_id, "name": name, "status": "error", "error": error}

    _connect_network(project)

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


def _rewrite_build_contexts(compose_file: str, workspace: str):
    """Rewrite relative build contexts (e.g. 'build: .') to absolute paths.

    Container and host share the same mount path, so absolute paths work for both
    the Docker CLI (in container) and the Docker daemon (on host).
    """
    try:
        with open(compose_file) as f:
            compose = yaml.safe_load(f)

        if not compose or "services" not in compose:
            return

        changed = False
        for svc_name, svc in compose.get("services", {}).items():
            build = svc.get("build")
            if build is None:
                continue

            if isinstance(build, str):
                if build in (".", "./"):
                    svc["build"] = workspace
                    changed = True
                elif build.startswith("./"):
                    svc["build"] = os.path.join(workspace, build[2:])
                    changed = True

            elif isinstance(build, dict):
                ctx = build.get("context", ".")
                if ctx in (".", "./"):
                    build["context"] = workspace
                    changed = True
                elif ctx.startswith("./"):
                    build["context"] = os.path.join(workspace, ctx[2:])
                    changed = True

        if changed:
            with open(compose_file, "w") as f:
                yaml.dump(compose, f, default_flow_style=False, sort_keys=False)

    except Exception as e:
        logger.warning(f"Failed to rewrite build contexts: {e}")


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

        # Remove ALL existing traefik labels (clean slate)
        old_labels = svc.get("labels", [])
        if isinstance(old_labels, dict):
            old_labels = [f"{k}={v}" for k, v in old_labels.items()]
        labels = [l for l in old_labels if not l.startswith("traefik.")]

        # Add fresh traefik labels
        labels.extend([
            "traefik.enable=true",
            f"traefik.http.routers.{router}.rule=Host(`{domain}`)",
            f"traefik.http.routers.{router}.entrypoints=web",
            f"traefik.http.services.{router}.loadbalancer.server.port={internal_port}",
        ])

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
