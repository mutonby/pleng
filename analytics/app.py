"""Built-in analytics — lightweight, API-first, no external dependencies.

Stores pageviews in SQLite. Serves the tracking script.
Any site deployed on Pleng can be tracked automatically.
"""
import hashlib
import logging
import os
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger("analytics")

DB_PATH = os.environ.get("DATABASE_PATH", "/data/analytics.db")

app = FastAPI(title="Pleng Analytics", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn.cursor()
        conn.commit()
    finally:
        conn.close()


@app.on_event("startup")
def init_db():
    with _conn() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS pageviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT NOT NULL,
                page TEXT NOT NULL,
                referrer TEXT DEFAULT '',
                source TEXT DEFAULT '',
                visitor_hash TEXT NOT NULL,
                date TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_pv_domain_date ON pageviews(domain, date);
            CREATE INDEX IF NOT EXISTS idx_pv_created ON pageviews(created_at);

            CREATE TABLE IF NOT EXISTS sites (
                domain TEXT PRIMARY KEY,
                created_at TEXT NOT NULL
            );
        """)
    logger.info("Analytics DB ready")


# ── Collector ───────────────────────────────────────────

@app.post("/api/collect")
async def collect(request: Request):
    data = await request.json()
    domain = data.get("d", "")
    page = data.get("p", "/")
    referrer = data.get("r", "")

    if not domain:
        return Response(status_code=204)

    ip = request.client.host or ""
    visitor_hash = hashlib.sha256(f"{ip}:{domain}:{datetime.utcnow().strftime('%Y-%m-%d')}".encode()).hexdigest()[:16]
    source = _extract_source(referrer)
    now = datetime.utcnow()

    with _conn() as c:
        c.execute(
            "INSERT INTO pageviews (domain, page, referrer, source, visitor_hash, date, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (domain, page, referrer, source, visitor_hash, now.strftime("%Y-%m-%d"), now.isoformat()),
        )
        # Auto-register site
        c.execute("INSERT OR IGNORE INTO sites (domain, created_at) VALUES (?, ?)", (domain, now.isoformat()))

    return Response(status_code=204)


@app.options("/api/collect")
async def collect_options():
    return Response(status_code=204, headers={
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST",
        "Access-Control-Allow-Headers": "Content-Type",
    })


# ── Tracking script ─────────────────────────────────────

@app.get("/t.js")
async def tracking_script():
    return FileResponse("/app/static/t.js", media_type="application/javascript",
                        headers={"Cache-Control": "public, max-age=3600"})


# ── Stats API ───────────────────────────────────────────

@app.get("/api/analytics/{domain}/stats")
async def stats(domain: str, period: str = "7d"):
    start = _period_start(period)
    with _conn() as c:
        c.execute(
            "SELECT COUNT(*) as pageviews, COUNT(DISTINCT visitor_hash) as visitors FROM pageviews WHERE domain = ? AND created_at >= ?",
            (domain, start),
        )
        row = dict(c.fetchone())
    return row


@app.get("/api/analytics/{domain}/pages")
async def top_pages(domain: str, period: str = "7d", limit: int = 10):
    start = _period_start(period)
    with _conn() as c:
        c.execute(
            "SELECT page, COUNT(*) as views, COUNT(DISTINCT visitor_hash) as visitors FROM pageviews WHERE domain = ? AND created_at >= ? GROUP BY page ORDER BY views DESC LIMIT ?",
            (domain, start, limit),
        )
        return [dict(r) for r in c.fetchall()]


@app.get("/api/analytics/{domain}/sources")
async def top_sources(domain: str, period: str = "7d", limit: int = 10):
    start = _period_start(period)
    with _conn() as c:
        c.execute(
            "SELECT source, COUNT(DISTINCT visitor_hash) as visitors FROM pageviews WHERE domain = ? AND created_at >= ? AND source != '' GROUP BY source ORDER BY visitors DESC LIMIT ?",
            (domain, start, limit),
        )
        return [dict(r) for r in c.fetchall()]


@app.get("/api/analytics/{domain}/daily")
async def daily(domain: str, period: str = "30d"):
    start = _period_start(period)
    with _conn() as c:
        c.execute(
            "SELECT date, COUNT(*) as pageviews, COUNT(DISTINCT visitor_hash) as visitors FROM pageviews WHERE domain = ? AND created_at >= ? GROUP BY date ORDER BY date",
            (domain, start),
        )
        return [dict(r) for r in c.fetchall()]


@app.get("/api/analytics/sites")
async def list_sites():
    with _conn() as c:
        c.execute("SELECT domain, created_at FROM sites ORDER BY created_at DESC")
        return [dict(r) for r in c.fetchall()]


# ── Internal ────────────────────────────────────────────

def _period_start(period: str) -> str:
    now = datetime.utcnow()
    deltas = {"24h": 1, "7d": 7, "30d": 30, "90d": 90}
    days = deltas.get(period, 7)
    return (now - timedelta(days=days)).isoformat()


def _extract_source(referrer: str) -> str:
    if not referrer:
        return ""
    from urllib.parse import urlparse
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
