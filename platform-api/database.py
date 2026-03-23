"""SQLite database for platform state."""
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime

DB_PATH = os.environ.get("DATABASE_PATH", "/data/pleng.db")


def init():
    with _conn() as c:
        c.executescript("""
            -- Migrations for existing DBs
            PRAGMA foreign_keys = OFF;
        """)
        # Add consecutive_failures column if missing
        try:
            c.execute("ALTER TABLE sites ADD COLUMN consecutive_failures INTEGER DEFAULT 0")
        except Exception:
            pass  # Column already exists

        c.executescript("""
            CREATE TABLE IF NOT EXISTS sites (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                status TEXT NOT NULL DEFAULT 'staging',
                staging_domain TEXT,
                production_domain TEXT,
                deploy_mode TEXT DEFAULT 'compose',
                project_path TEXT,
                github_url TEXT,
                description TEXT,
                ai_cost REAL DEFAULT 0,
                consecutive_failures INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                deployed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS site_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id TEXT NOT NULL,
                message TEXT NOT NULL,
                level TEXT DEFAULT 'info',
                created_at TEXT NOT NULL,
                FOREIGN KEY (site_id) REFERENCES sites(id)
            );
            CREATE INDEX IF NOT EXISTS idx_site_logs_site ON site_logs(site_id);

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn.cursor()
        conn.commit()
    finally:
        conn.close()


# ── Sites ───────────────────────────────────────────────

def create_site(name: str, deploy_mode: str = "compose", description: str = "",
                github_url: str = "", project_path: str = "") -> dict:
    site_id = uuid.uuid4().hex[:12]
    now = datetime.utcnow().isoformat()
    with _conn() as c:
        c.execute(
            """INSERT INTO sites (id, name, status, deploy_mode, description,
               github_url, project_path, created_at, updated_at)
               VALUES (?, ?, 'deploying', ?, ?, ?, ?, ?, ?)""",
            (site_id, name, deploy_mode, description, github_url, project_path, now, now),
        )
    return get_site(site_id)


def get_site(site_id: str) -> dict | None:
    with _conn() as c:
        c.execute("SELECT * FROM sites WHERE id = ?", (site_id,))
        row = c.fetchone()
        return dict(row) if row else None


def get_site_by_name(name: str) -> dict | None:
    with _conn() as c:
        c.execute("SELECT * FROM sites WHERE name = ?", (name,))
        row = c.fetchone()
        return dict(row) if row else None


def get_all_sites() -> list[dict]:
    with _conn() as c:
        c.execute("SELECT * FROM sites ORDER BY created_at DESC")
        return [dict(r) for r in c.fetchall()]


def update_site(site_id: str, **kwargs):
    kwargs["updated_at"] = datetime.utcnow().isoformat()
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [site_id]
    with _conn() as c:
        c.execute(f"UPDATE sites SET {sets} WHERE id = ?", vals)


def delete_site(site_id: str):
    with _conn() as c:
        c.execute("DELETE FROM site_logs WHERE site_id = ?", (site_id,))
        c.execute("DELETE FROM sites WHERE id = ?", (site_id,))


def add_site_log(site_id: str, message: str, level: str = "info"):
    now = datetime.utcnow().isoformat()
    with _conn() as c:
        c.execute(
            "INSERT INTO site_logs (site_id, message, level, created_at) VALUES (?, ?, ?, ?)",
            (site_id, message, level, now),
        )


def get_site_logs(site_id: str, limit: int = 50) -> list[dict]:
    with _conn() as c:
        c.execute(
            "SELECT * FROM site_logs WHERE site_id = ? ORDER BY created_at DESC LIMIT ?",
            (site_id, limit),
        )
        return [dict(r) for r in c.fetchall()]


# ── Health monitoring ────────────────────────────────────

def increment_failures(site_id: str) -> int:
    """Increment consecutive failures and return new count."""
    with _conn() as c:
        c.execute("UPDATE sites SET consecutive_failures = consecutive_failures + 1 WHERE id = ?", (site_id,))
        c.execute("SELECT consecutive_failures FROM sites WHERE id = ?", (site_id,))
        row = c.fetchone()
        return row["consecutive_failures"] if row else 0


def get_failures(site_id: str) -> int:
    with _conn() as c:
        c.execute("SELECT consecutive_failures FROM sites WHERE id = ?", (site_id,))
        row = c.fetchone()
        return row["consecutive_failures"] if row else 0


def reset_failures(site_id: str):
    with _conn() as c:
        c.execute("UPDATE sites SET consecutive_failures = 0 WHERE id = ?", (site_id,))


# ── Settings / API Key ──────────────────────────────────

def get_setting(key: str) -> str | None:
    with _conn() as c:
        c.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = c.fetchone()
        return row["value"] if row else None


def set_setting(key: str, value: str):
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))


def get_or_create_api_key() -> str:
    """Get existing API key or generate a new one on first boot."""
    import secrets
    key = get_setting("api_key")
    if not key:
        key = "pleng_" + secrets.token_hex(24)
        set_setting("api_key", key)
    return key
