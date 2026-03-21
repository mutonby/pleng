# Pleng — Self-hosted AI-Native PaaS

## Architecture
6 containers, one `docker compose up`:
- **traefik** — reverse proxy + SSL (sslip.io staging, Let's Encrypt production)
- **platform-api** — FastAPI, orchestrates Docker, owns state (SQLite)
- **agent** — Claude Code in a container, has `pleng` CLI to call platform-api
- **telegram-bot** — bridges Telegram ↔ agent
- **analytics** — pageview collector + SQLite + API
- **dashboard** — React static app (nginx)

## Key directories
```
platform-api/   FastAPI + SQLite + Docker deployer
agent/          Claude Code + Flask server + pleng CLI
telegram-bot/   python-telegram-bot → agent HTTP
analytics/      FastAPI + SQLite pageview tracking
dashboard/      React + Vite + Tailwind
```

## Dev commands
```bash
make up       # docker compose up --build -d
make down     # stop all
make logs     # all logs
make chat     # terminal chat with agent
make ps       # container status
```

## Coding standards
- Python: PEP 8, type hints
- Frontend: React + TypeScript, Tailwind
- Services communicate via HTTP (internal Docker network)
- Agent NEVER touches Docker directly — always goes through platform-api
