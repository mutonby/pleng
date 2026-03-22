"""Agent HTTP server — receives messages, runs Claude Code, returns response.

Telegram-bot and dashboard POST here. Claude Code runs in /projects with
the pleng CLI tool available for deploying, logs, etc.
"""
import getpass
import json
import logging
import os
import subprocess
import sys
import threading

from flask import Flask, jsonify, request

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger("agent")

app = Flask(__name__)

# Session persistence: chat_id -> claude session_id
_sessions: dict[str, str] = {}
_lock = threading.Lock()

WORKSPACE = os.environ.get("PROJECTS_DIR", "/opt/pleng/projects")
MODEL = os.environ.get("MODEL_NAME", "claude-sonnet-4-20250514")
PLATFORM_API_URL = os.environ.get("PLATFORM_API_URL", "http://platform-api:8000")

# Fetch API key from platform-api on startup
_platform_api_key = ""


def _fetch_api_key():
    """Fetch API key from platform-api (internal network, no auth needed)."""
    global _platform_api_key
    import time
    import requests
    for attempt in range(30):
        try:
            r = requests.get(f"{PLATFORM_API_URL}/internal/key", timeout=5)
            if r.status_code == 200:
                _platform_api_key = r.json().get("api_key", "")
                logger.info(f"Got API key from platform-api: {_platform_api_key[:12]}...")
                return
        except Exception:
            pass
        logger.info(f"Waiting for platform-api... (attempt {attempt + 1})")
        time.sleep(2)
    logger.warning("Could not fetch API key from platform-api")


# Fetch on import (runs in background)
threading.Thread(target=_fetch_api_key, daemon=True).start()


@app.route("/chat", methods=["POST"])
def chat():
    """Send a message to Claude Code and get the response."""
    data = request.get_json() or {}
    message = data.get("message", "")
    session_key = data.get("session_id", "default")

    if not message:
        return jsonify({"error": "message required"}), 400

    logger.info(f"Chat [{session_key}]: {message[:80]}...")

    with _lock:
        resume_id = _sessions.get(session_key)

    result_text, new_session_id, error = _run_claude(message, resume_id)

    if new_session_id:
        with _lock:
            _sessions[session_key] = new_session_id

    if error and not result_text:
        return jsonify({"response": f"Error: {error}", "session_id": new_session_id})

    return jsonify({"response": result_text, "session_id": new_session_id})


@app.route("/chat/stream", methods=["POST"])
def chat_stream():
    """Streaming version — sends chunks as newline-delimited JSON."""
    from flask import Response

    data = request.get_json() or {}
    message = data.get("message", "")
    session_key = data.get("session_id", "default")

    if not message:
        return jsonify({"error": "message required"}), 400

    logger.info(f"Stream [{session_key}]: {message[:80]}...")

    with _lock:
        resume_id = _sessions.get(session_key)

    def generate():
        result_text, session_id, error = _run_claude_streaming(message, resume_id)

        if session_id:
            with _lock:
                _sessions[session_key] = session_id

        if error and not result_text:
            yield json.dumps({"chunk": f"Error: {error}", "done": True}) + "\n"
        elif result_text:
            yield json.dumps({"chunk": result_text, "done": True}) + "\n"
        else:
            yield json.dumps({"chunk": "No response.", "done": True}) + "\n"

    return Response(generate(), mimetype="application/x-ndjson")


@app.route("/chat/reset", methods=["POST"])
def reset():
    data = request.get_json() or {}
    session_key = data.get("session_id", "default")
    with _lock:
        _sessions.pop(session_key, None)
    return jsonify({"ok": True})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


def _run_claude(message: str, resume_session: str = None) -> tuple[str, str | None, str | None]:
    """Run Claude Code CLI and return (response_text, session_id, error)."""
    env = os.environ.copy()
    env["CLAUDE_CODE_NON_INTERACTIVE"] = "true"
    env["CLAUDE_CODE_ACCEPT_TOS"] = "true"

    # Auth: API key or OAuth
    auth_mode = os.environ.get("CLAUDE_AUTH_MODE", "oauth")
    if auth_mode == "api_key" and env.get("ANTHROPIC_API_KEY"):
        env["HOME"] = "/tmp"
    else:
        # OAuth mode — use claude user's home with .claude.json
        env.pop("ANTHROPIC_API_KEY", None)
        env["HOME"] = "/home/claude"

    cmd = [
        "claude", "-p", message,
        "--output-format", "stream-json",
        "--verbose",
        "--dangerously-skip-permissions",
    ]

    if resume_session:
        cmd.extend(["--resume", resume_session])

    if MODEL:
        cmd.extend(["--model", MODEL])

    # Run as claude user if we're root
    if getpass.getuser() == "root":
        env_args = [
            f"HOME={env.get('HOME', '/home/claude')}",
            "CLAUDE_CODE_NON_INTERACTIVE=true",
            "CLAUDE_CODE_ACCEPT_TOS=true",
        ]
        if env.get("ANTHROPIC_API_KEY"):
            env_args.append(f"ANTHROPIC_API_KEY={env['ANTHROPIC_API_KEY']}")
        # Pass platform API URL + key for pleng CLI
        api_url = env.get("PLATFORM_API_URL", "http://platform-api:8000")
        env_args.append(f"PLATFORM_API_URL={api_url}")
        if _platform_api_key:
            env_args.append(f"PLENG_API_KEY={_platform_api_key}")

        cmd = ["sudo", "-u", "claude", "env"] + env_args + cmd

    try:
        process = subprocess.Popen(
            cmd, cwd=WORKSPACE,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, text=True, env=env, bufsize=1,
        )

        result_text = ""
        session_id = None
        error = None

        for line in iter(process.stdout.readline, ""):
            try:
                event = json.loads(line)
                etype = event.get("type")

                if event.get("session_id"):
                    session_id = event["session_id"]

                if etype == "result":
                    result_text = event.get("result", "")

            except json.JSONDecodeError:
                pass

        process.stdout.close()
        rc = process.wait(timeout=600)

        if rc != 0 and not result_text:
            error = f"Claude Code exited with code {rc}"

        return result_text, session_id, error

    except subprocess.TimeoutExpired:
        process.kill()
        return "", None, "Claude Code timed out"
    except Exception as e:
        return "", None, str(e)


# Streaming uses the same implementation — Claude Code outputs final result
_run_claude_streaming = _run_claude


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
