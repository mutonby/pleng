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

WORKSPACE = "/projects"
MODEL = os.environ.get("MODEL_NAME", "claude-sonnet-4-20250514")


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

    if env.get("ANTHROPIC_API_KEY"):
        env["HOME"] = "/tmp"
    else:
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
        # Pass platform API URL for pleng CLI
        api_url = env.get("PLATFORM_API_URL", "http://platform-api:8000")
        env_args.append(f"PLATFORM_API_URL={api_url}")

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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
