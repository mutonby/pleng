#!/bin/bash
# Copy OAuth credentials from read-only mount to claude user's home
if [ -f /tmp/.claude.json.host ]; then
    cp /tmp/.claude.json.host /home/claude/.claude.json
    chown claude:claude /home/claude/.claude.json
    chmod 600 /home/claude/.claude.json
    echo "OAuth credentials copied to /home/claude/.claude.json"
fi

# Fix permissions
chown -R claude:claude /home/claude/.claude 2>/dev/null || true
chown -R claude:claude /projects 2>/dev/null || true

# Setup workspace CLAUDE.md
cp /app/workspace/CLAUDE.md /projects/CLAUDE.md 2>/dev/null || true
chown -R claude:claude /projects

exec python /app/server.py
