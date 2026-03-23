"""Analytics from Traefik access logs — zero-install, no tracking scripts needed.

Parses Traefik's JSON access logs to extract:
- Pageviews per site (by Host header)
- Unique visitors (by hashed IP)
- Top pages
- Top referrers
- Response times
- Error rates

Runs every 5 minutes, aggregates into SQLite.
"""
import hashlib
import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta
from urllib.parse import urlparse

import database as db

logger = logging.getLogger("analytics")

ACCESS_LOG = "/var/log/traefik/access.log"
PARSE_INTERVAL = 300  # 5 minutes
_last_position = 0  # Track where we left off in the log file


def start():
    """Start the analytics parser thread."""
    thread = threading.Thread(target=_parse_loop, daemon=True)
    thread.start()
    logger.info("Analytics parser started")


def _parse_loop():
    global _last_position
    time.sleep(60)  # Wait for Traefik to start logging

    while True:
        try:
            _parse_new_entries()
        except Exception as e:
            logger.error(f"Analytics parse error: {e}")
        time.sleep(PARSE_INTERVAL)


def _parse_new_entries():
    """Read new lines from Traefik access log and aggregate them."""
    global _last_position

    if not os.path.exists(ACCESS_LOG):
        return

    entries = []
    with open(ACCESS_LOG, "r") as f:
        f.seek(_last_position)
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                parsed = _parse_entry(entry)
                if parsed:
                    entries.append(parsed)
            except (json.JSONDecodeError, Exception):
                continue
        _last_position = f.tell()

    if entries:
        _store_entries(entries)
        logger.info(f"Parsed {len(entries)} access log entries")


def _parse_entry(entry: dict) -> dict | None:
    """Extract useful fields from a Traefik JSON log entry."""
    # Get the request host (domain)
    request = entry.get("RequestHost", "") or entry.get("request", {}).get("host", "")
    if not request:
        # Try from RouterName
        router = entry.get("RouterName", "")
        if "@" in router:
            request = router.split("@")[0]

    if not request:
        return None

    # Skip Pleng's own panel traffic
    if "panel." in request:
        return None

    # Skip requests by IP (bots scanning the server)
    if request.replace(".", "").isdigit():
        return None

    # Skip health monitor (Docker internal IPs)
    client_ip = entry.get("ClientAddr", "") or entry.get("ClientHost", "")
    if client_ip.startswith("172.") or client_ip.startswith("10.") or client_ip.startswith("192.168."):
        return None

    # Get path
    path = entry.get("RequestPath", "") or entry.get("request", {}).get("path", "/")

    # Skip static assets for cleaner analytics
    if any(path.endswith(ext) for ext in (".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".woff2", ".map")):
        return None

    # Get client IP and hash it for privacy
    client_ip = entry.get("ClientAddr", "") or entry.get("ClientHost", "")
    if ":" in client_ip:
        client_ip = client_ip.rsplit(":", 1)[0]  # Remove port
    visitor_hash = hashlib.sha256(f"{client_ip}:{request}:{datetime.utcnow().strftime('%Y-%m-%d')}".encode()).hexdigest()[:12]

    # Status code
    status = entry.get("DownstreamStatus", 0) or entry.get("downstream", {}).get("status", 0)

    # Response time (ms)
    duration = entry.get("Duration", 0)
    if duration:
        duration_ms = duration / 1_000_000  # nanoseconds to ms
    else:
        duration_ms = 0

    # Referrer
    referrer = ""
    headers = entry.get("request", {}).get("headers", {})
    if isinstance(headers, dict):
        ref_list = headers.get("Referer", []) or headers.get("referer", [])
        if ref_list and isinstance(ref_list, list):
            referrer = ref_list[0]
        elif isinstance(ref_list, str):
            referrer = ref_list

    return {
        "domain": request.lower(),
        "path": path,
        "visitor_hash": visitor_hash,
        "status": int(status) if status else 0,
        "duration_ms": round(duration_ms, 1),
        "referrer": _extract_source(referrer),
        "timestamp": datetime.utcnow().isoformat(),
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
    }


def _store_entries(entries: list[dict]):
    """Store parsed entries in SQLite."""
    with db._conn() as c:
        for e in entries:
            c.execute(
                """INSERT INTO traffic
                   (domain, path, visitor_hash, status, duration_ms, referrer, date, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (e["domain"], e["path"], e["visitor_hash"], e["status"],
                 e["duration_ms"], e["referrer"], e["date"], e["timestamp"]),
            )


def _extract_source(referrer: str) -> str:
    if not referrer:
        return ""
    try:
        host = urlparse(referrer).netloc.lower().removeprefix("www.")
        sources = {
            "google.": "Google", "bing.com": "Bing", "duckduckgo.com": "DuckDuckGo",
            "twitter.com": "Twitter", "x.com": "Twitter", "t.co": "Twitter",
            "facebook.com": "Facebook", "linkedin.com": "LinkedIn",
            "reddit.com": "Reddit", "github.com": "GitHub",
        }
        for pattern, name in sources.items():
            if pattern in host:
                return name
        return host
    except Exception:
        return ""


# ── Query functions (called by API) ─────────────────────

def get_site_stats(domain: str, period: str = "7d") -> dict:
    start = _period_start(period)
    with db._conn() as c:
        c.execute(
            """SELECT COUNT(*) as pageviews, COUNT(DISTINCT visitor_hash) as visitors
               FROM traffic WHERE domain = ? AND created_at >= ?""",
            (domain, start),
        )
        row = dict(c.fetchone())

        c.execute(
            """SELECT AVG(duration_ms) as avg_response_ms,
                      SUM(CASE WHEN status >= 500 THEN 1 ELSE 0 END) as errors
               FROM traffic WHERE domain = ? AND created_at >= ?""",
            (domain, start),
        )
        perf = dict(c.fetchone())

    return {
        "pageviews": row["pageviews"],
        "visitors": row["visitors"],
        "avg_response_ms": round(perf["avg_response_ms"] or 0, 1),
        "errors": perf["errors"] or 0,
        "period": period,
    }


def get_top_pages(domain: str, period: str = "7d", limit: int = 10) -> list:
    start = _period_start(period)
    with db._conn() as c:
        c.execute(
            """SELECT path, COUNT(*) as views, COUNT(DISTINCT visitor_hash) as visitors
               FROM traffic WHERE domain = ? AND created_at >= ?
               GROUP BY path ORDER BY views DESC LIMIT ?""",
            (domain, start, limit),
        )
        return [dict(r) for r in c.fetchall()]


def get_top_sources(domain: str, period: str = "7d", limit: int = 10) -> list:
    start = _period_start(period)
    with db._conn() as c:
        c.execute(
            """SELECT referrer as source, COUNT(DISTINCT visitor_hash) as visitors
               FROM traffic WHERE domain = ? AND created_at >= ? AND referrer != ''
               GROUP BY referrer ORDER BY visitors DESC LIMIT ?""",
            (domain, start, limit),
        )
        return [dict(r) for r in c.fetchall()]


def get_daily_stats(domain: str, period: str = "30d") -> list:
    start = _period_start(period)
    with db._conn() as c:
        c.execute(
            """SELECT date, COUNT(*) as pageviews, COUNT(DISTINCT visitor_hash) as visitors,
                      AVG(duration_ms) as avg_ms
               FROM traffic WHERE domain = ? AND created_at >= ?
               GROUP BY date ORDER BY date""",
            (domain, start),
        )
        return [dict(r) for r in c.fetchall()]


def _period_start(period: str) -> str:
    now = datetime.utcnow()
    deltas = {"24h": 1, "7d": 7, "30d": 30, "90d": 90}
    days = deltas.get(period, 7)
    return (now - timedelta(days=days)).isoformat()
