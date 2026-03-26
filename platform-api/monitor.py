"""Health monitor + maintenance scheduler + agent heartbeat.

- Health checks: pings deployed sites every 10 min, alerts + auto-restart via Telegram
- Docker prune: cleans unused images/cache every 24h
- Heartbeats: agent checks defined in heartbeat.md (quick/deep/full at different intervals)
"""
import html
import logging
import os
import subprocess
import threading
import time

import requests

import database as db
import deployer

logger = logging.getLogger("monitor")

CHECK_INTERVAL = int(os.environ.get("MONITOR_INTERVAL", "600"))  # 10 minutes
PRUNE_INTERVAL = 86400  # 24 hours
FAILURE_THRESHOLD = 3
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
AGENT_URL = os.environ.get("AGENT_URL", "http://agent:8000")
PROJECTS_DIR = os.environ.get("PROJECTS_DIR", "/opt/pleng/projects")
HEARTBEAT_FILE = os.path.join(PROJECTS_DIR, "heartbeat.md")
HEARTBEAT_DEFAULT = "/app/heartbeat.md"


def start():
    """Start background threads."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram not configured — monitor won't send alerts")

    threading.Thread(target=_health_loop, daemon=True).start()
    logger.info(f"Health monitor started (interval={CHECK_INTERVAL}s)")

    threading.Thread(target=_maintenance_loop, daemon=True).start()
    logger.info(f"Maintenance scheduler started (backup + prune every 24h)")

    # Copy default heartbeat.md to shared volume on first boot
    if not os.path.exists(HEARTBEAT_FILE) and os.path.exists(HEARTBEAT_DEFAULT):
        import shutil
        shutil.copy2(HEARTBEAT_DEFAULT, HEARTBEAT_FILE)
        logger.info(f"Copied default heartbeat.md to {HEARTBEAT_FILE}")

    heartbeats = _load_heartbeats(HEARTBEAT_FILE)
    for hb in heartbeats:
        threading.Thread(target=_run_heartbeat, args=(hb,), daemon=True).start()
        logger.info(f"Heartbeat [{hb['name']}] started (every {hb['interval_sec']}s)")


# ── Health checks ───────────────────────────────────────

def _health_loop():
    time.sleep(30)  # Wait for initial deploys
    while True:
        try:
            for site in db.get_all_sites():
                if site["status"] in ("staging", "production"):
                    _check_site(site)
        except Exception as e:
            logger.error(f"Health loop error: {e}")
        time.sleep(CHECK_INTERVAL)


def _check_site(site: dict):
    domain = site.get("production_domain") or site.get("staging_domain")
    if not domain:
        return

    url = f"https://{domain}" if site.get("production_domain") else f"http://{domain}"

    try:
        r = requests.get(url, timeout=10, allow_redirects=True)
        if r.status_code < 500:
            _mark_healthy(site)
        else:
            _mark_failure(site, f"HTTP {r.status_code}")
    except requests.ConnectionError:
        _mark_failure(site, "Connection refused")
    except requests.Timeout:
        _mark_failure(site, "Timeout")
    except Exception as e:
        _mark_failure(site, str(e)[:100])


def _mark_failure(site: dict, error: str):
    failures = db.increment_failures(site["id"])
    logger.warning(f"{site['name']}: failure #{failures} — {error}")

    if failures == FAILURE_THRESHOLD:
        _alert(f"🔴 <b>{site['name']}</b> is DOWN\n{error}")
        ok = deployer.restart(site["id"])
        _alert(f"🔄 Auto-restart {'ok' if ok else 'FAILED'}: <b>{site['name']}</b>")
        db.add_site_log(site["id"], f"DOWN: {error}. Auto-restart {'ok' if ok else 'failed'}", level="warning")


def _mark_healthy(site: dict):
    failures = db.get_failures(site["id"])
    if failures >= FAILURE_THRESHOLD:
        _alert(f"🟢 <b>{site['name']}</b> is back UP")
        db.add_site_log(site["id"], "Recovered")
    if failures > 0:
        db.reset_failures(site["id"])


# ── Docker prune ────────────────────────────────────────

def _maintenance_loop():
    time.sleep(300)  # Wait 5 min after startup
    while True:
        try:
            _backup()
        except Exception as e:
            logger.error(f"Backup error: {e}")
        try:
            _docker_prune()
        except Exception as e:
            logger.error(f"Prune error: {e}")
        time.sleep(PRUNE_INTERVAL)


# ── Backups ─────────────────────────────────────────────

BACKUP_DIR = "/opt/pleng/backups"
BACKUP_KEEP = 7  # Keep last 7 backups

def _backup():
    """Backup SQLite DB + site compose files. Keeps last 7 days."""
    import glob
    import shutil
    import tarfile
    from datetime import datetime

    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H%M")
    backup_file = os.path.join(BACKUP_DIR, f"pleng-{timestamp}.tar.gz")

    db_path = os.environ.get("DATABASE_PATH", "/data/pleng.db")
    projects_dir = os.environ.get("PROJECTS_DIR", "/opt/pleng/projects")

    try:
        with tarfile.open(backup_file, "w:gz") as tar:
            # Backup SQLite DB
            if os.path.exists(db_path):
                tar.add(db_path, arcname="pleng.db")

            # Backup docker-compose files from each project (not full code — just configs)
            if os.path.exists(projects_dir):
                for name in os.listdir(projects_dir):
                    proj = os.path.join(projects_dir, name)
                    if not os.path.isdir(proj):
                        continue
                    for fname in ("docker-compose.yml", "docker-compose.pleng.yml", "Dockerfile", ".env"):
                        fpath = os.path.join(proj, fname)
                        if os.path.exists(fpath):
                            tar.add(fpath, arcname=f"projects/{name}/{fname}")

        size = os.path.getsize(backup_file)
        size_str = f"{size / 1024:.1f}KB" if size < 1048576 else f"{size / 1048576:.1f}MB"
        logger.info(f"Backup created: {backup_file} ({size_str})")

        # Clean old backups
        backups = sorted(glob.glob(os.path.join(BACKUP_DIR, "pleng-*.tar.gz")))
        while len(backups) > BACKUP_KEEP:
            old = backups.pop(0)
            os.remove(old)
            logger.info(f"Deleted old backup: {old}")

        sites_count = len(db.get_all_sites())
        _alert(f"💾 Backup done: {size_str}, {sites_count} sites")

    except Exception as e:
        logger.error(f"Backup failed: {e}")
        _alert(f"⚠️ Backup failed: {e}")


# ── Docker prune ────────────────────────────────────────

def _docker_prune():
    """Remove unused Docker images and build cache."""
    r1 = subprocess.run(
        ["docker", "image", "prune", "-f"],
        capture_output=True, text=True, timeout=120,
    )
    r2 = subprocess.run(
        ["docker", "builder", "prune", "-f", "--filter", "until=168h"],
        capture_output=True, text=True, timeout=120,
    )

    freed1 = r1.stdout.strip().split("\n")[-1] if r1.stdout else "0B"
    freed2 = r2.stdout.strip().split("\n")[-1] if r2.stdout else "0B"
    logger.info(f"Docker prune: images={freed1}, cache={freed2}")

    if "0B" not in freed1 or "0B" not in freed2:
        _alert(f"🧹 Docker cleanup: {freed1}, {freed2}")


# ── Agent heartbeats (from heartbeat.md) ──────────────

def _load_heartbeats(path: str) -> list[dict]:
    """Parse heartbeat.md into list of {name, interval_sec, prompt}."""
    try:
        with open(path) as f:
            content = f.read()
    except FileNotFoundError:
        logger.warning(f"Heartbeat file not found: {path} — no heartbeats will run")
        return []

    heartbeats = []
    sections = content.split("\n## ")[1:]  # Skip everything before first ##

    for section in sections:
        lines = section.strip().split("\n")
        header = lines[0]

        # Parse "quick | 5m"
        parts = header.split("|")
        if len(parts) < 2:
            continue
        name = parts[0].strip()
        interval_str = parts[1].strip()

        # Parse interval: "5m" → 300, "120m" → 7200
        try:
            interval_sec = int(interval_str.rstrip("m")) * 60
        except ValueError:
            logger.warning(f"Heartbeat [{name}]: invalid interval '{interval_str}', skipping")
            continue

        prompt = "\n".join(lines[1:]).strip()
        if not prompt:
            continue

        heartbeats.append({"name": name, "interval_sec": interval_sec, "prompt": prompt})
        logger.info(f"Loaded heartbeat: {name} (every {interval_sec}s)")

    return heartbeats


def _run_heartbeat(hb: dict):
    """Run a heartbeat check on its interval forever."""
    name = hb["name"]
    interval = hb["interval_sec"]
    prompt = hb["prompt"]
    # Same session as the user's Telegram chat — one single conversation thread
    session_id = TELEGRAM_CHAT_ID or "heartbeat"
    emoji = {"quick": "⚡", "deep": "🔍", "full": "📋"}.get(name, "🔍")

    # First run: wait one full interval
    time.sleep(interval)

    while True:
        try:
            logger.info(f"Heartbeat [{name}] starting...")

            response = _ask_agent(prompt, session_id=session_id)

            if not response:
                logger.warning(f"Heartbeat [{name}]: agent did not respond")
            elif response.strip().upper() == "OK":
                # Silent when everything is fine (any level)
                logger.info(f"Heartbeat [{name}]: OK")
            else:
                safe = html.escape(response)
                msg = f"{emoji} <b>Heartbeat {name}</b>\n\n{safe}"
                if len(msg) > 4000:
                    msg = msg[:3997] + "..."
                _alert(msg)
                logger.info(f"Heartbeat [{name}]: reported")

        except Exception as e:
            logger.error(f"Heartbeat [{name}] error: {e}")

        time.sleep(interval)


def _ask_agent(prompt: str, session_id: str = "heartbeat") -> str | None:
    """Send a prompt to the agent and return the response text."""
    try:
        r = requests.post(
            f"{AGENT_URL}/chat",
            json={"message": prompt, "session_id": session_id},
            timeout=300,
        )
        if r.status_code == 200:
            return r.json().get("response", "")
        logger.error(f"Agent returned HTTP {r.status_code}: {r.text[:200]}")
        return None
    except requests.Timeout:
        logger.error("Agent request timed out (300s)")
        return None
    except requests.ConnectionError:
        logger.error("Cannot connect to agent — is it running?")
        return None
    except Exception as e:
        logger.error(f"Agent request failed: {e}")
        return None


# ── Telegram ────────────────────────────────────────────

def _alert(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.info(f"Alert (no Telegram): {message}")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        logger.error(f"Telegram alert failed: {e}")
