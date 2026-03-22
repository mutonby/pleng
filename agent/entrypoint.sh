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

PROJECTS=${PROJECTS_DIR:-/opt/pleng/projects}
mkdir -p "$PROJECTS"
chown -R claude:claude "$PROJECTS" 2>/dev/null || true

# Write env vars to claude user's profile so ALL bash subprocesses inherit them
cat > /home/claude/.bashrc << BASHRC
export PLATFORM_API_URL="${PLATFORM_API_URL:-http://platform-api:8000}"
export PLENG_API_KEY="${PLENG_API_KEY:-}"
export PROJECTS_DIR="$PROJECTS"
BASHRC
chown claude:claude /home/claude/.bashrc

# Also write to /etc/environment as fallback
echo "PLATFORM_API_URL=${PLATFORM_API_URL:-http://platform-api:8000}" >> /etc/environment
echo "PROJECTS_DIR=$PROJECTS" >> /etc/environment

# Setup workspace CLAUDE.md
cp /app/workspace/CLAUDE.md "$PROJECTS/CLAUDE.md" 2>/dev/null || true

exec python /app/server.py
