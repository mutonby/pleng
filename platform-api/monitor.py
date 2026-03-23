"""Health monitor — checks deployed sites every 60s and alerts via Telegram.

- Pings each site's public URL
- After 3 consecutive failures: sends Telegram alert + auto-restarts
- When recovered: sends recovery alert
"""
import logging
import os
import threading
import time

import requests

import database as db
import deployer

logger = logging.getLogger("monitor")

CHECK_INTERVAL = int(os.environ.get("MONITOR_INTERVAL", "600"))  # 10 minutes
FAILURE_THRESHOLD = 3
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def start():
    """Start the background monitoring thread."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram not configured — monitor will check sites but won't send alerts")
    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()
    logger.info(f"Health monitor started (interval={CHECK_INTERVAL}s, threshold={FAILURE_THRESHOLD})")


def _loop():
    # Wait for initial deploys to settle
    time.sleep(30)

    while True:
        try:
            sites = db.get_all_sites()
            for site in sites:
                if site["status"] in ("staging", "production"):
                    _check_site(site)
        except Exception as e:
            logger.error(f"Monitor loop error: {e}")
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
        _mark_failure(site, "Timeout (10s)")
    except Exception as e:
        _mark_failure(site, str(e)[:100])


def _mark_failure(site: dict, error: str):
    failures = db.increment_failures(site["id"])
    logger.warning(f"{site['name']}: failure #{failures} — {error}")

    if failures == FAILURE_THRESHOLD:
        _alert(f"🔴 <b>{site['name']}</b> is DOWN\n{error}")
        # Try auto-restart
        logger.info(f"Auto-restarting {site['name']}...")
        ok = deployer.restart(site["id"])
        if ok:
            _alert(f"🔄 Auto-restarted <b>{site['name']}</b>")
        else:
            _alert(f"⚠️ Auto-restart failed for <b>{site['name']}</b>")
        db.add_site_log(site["id"], f"Health check failed ({error}), auto-restart {'ok' if ok else 'failed'}", level="warning")


def _mark_healthy(site: dict):
    failures = db.get_failures(site["id"])
    if failures >= FAILURE_THRESHOLD:
        _alert(f"🟢 <b>{site['name']}</b> is back UP")
        db.add_site_log(site["id"], "Recovered after health check failure")
    if failures > 0:
        db.reset_failures(site["id"])


def _alert(message: str):
    """Send alert via Telegram."""
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
