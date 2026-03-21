#!/bin/bash
# Setup workspace CLAUDE.md
cp /app/workspace/CLAUDE.md /projects/CLAUDE.md 2>/dev/null || true
chown -R claude:claude /projects

exec python /app/server.py
