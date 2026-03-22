<p align="center">
  <h1 align="center">Pleng</h1>
  <p align="center"><strong>The first self-hosted, AI-native PaaS.</strong></p>
  <p align="center">
    Install on any VPS. Deploy apps by talking to an AI agent.<br/>
    Telegram, terminal, or any external AI tool via skill.md.
  </p>
</p>

<p align="center">
  <a href="#quickstart">Quickstart</a> · <a href="#how-it-works">How it works</a> · <a href="#the-4-doors">The 4 doors</a> · <a href="#architecture">Architecture</a> · <a href="#roadmap">Roadmap</a>
</p>

---

## The problem

Millions of devs use Claude Code, Cursor, Windsurf to generate code. Then they hit a wall:

> *"We're vibe coding in 2026. Why are we still deploying like it's 2018?"*

- **Bolt / Lovable / Replit** — have hosting, but it's limited and vendor-locked.
- **Claude Code / Cursor / Windsurf** — generate code, but have zero deploy story.
- **Coolify / Dokploy** (50K+ stars) — self-hosted PaaS, but no AI. Passive dashboards for humans.
- **Pulumi Neo / StackGen** — AI DevOps, but cloud-only, $10K+/month, enterprise.

The quadrant **"self-hosted + AI-native"** is completely empty. Pleng fills it.

## Quickstart

```bash
git clone https://github.com/your-org/pleng
cd pleng
cp .env.example .env
# Edit .env with your keys (see below)
docker compose up -d
```

That's it. 6 containers start up. You now have:

| What | Where |
|---|---|
| **Dashboard** | `http://panel.YOUR-IP.sslip.io` |
| **Telegram bot** | `@your_bot` (listening) |
| **Terminal** | `make chat` on the VPS |
| **skill.md** | `http://panel.YOUR-IP.sslip.io/skill.md` |
| **API key** | `docker compose logs platform-api` (printed on startup) |

### Required env vars

```bash
ANTHROPIC_API_KEY=sk-ant-...       # For the AI agent (Claude Code)
TELEGRAM_BOT_TOKEN=123456:ABC...   # From @BotFather
TELEGRAM_CHAT_ID=123456789         # Your chat ID
PUBLIC_IP=89.141.205.249           # Your VPS public IP
```

## How it works

You tell the agent what you want. It does the rest.

```
You (Telegram): "hazme una API de reservas con Postgres"

Agent: creates /projects/reservas/
       writes app.py, Dockerfile, docker-compose.yml
       runs: pleng deploy /projects/reservas --name reservas

Platform API: docker compose up → Traefik labels → sslip.io subdomain

Agent: "Listo. http://a3f2.89.141.205.249.sslip.io"
```

Later:

```
You: "ponle reservas.midominio.com"

Agent: runs: pleng promote reservas --domain reservas.midominio.com

Platform API: updates Traefik → Let's Encrypt SSL

Agent: "Listo. https://reservas.midominio.com"
```

### The lifecycle

```
 ┌─────────┐    promote     ┌────────────┐
 │ STAGING │ ─────────────▶ │ PRODUCTION │
 │  free   │  custom domain │   HTTPS    │
 │ sslip.io│  + Let's       │            │
 └─────────┘  Encrypt       └────────────┘
      │                           │
      ▼                           ▼
   stop / remove              stop / remove
```

1. Everything starts as **staging** with a free `http://{hash}.{IP}.sslip.io` URL. No domain needed.
2. You can have 10 projects in staging with zero effort.
3. The ones you like, **promote** to production with a custom domain → automatic HTTPS.
4. The ones you don't, stop or remove.
5. No git, no CI/CD, no pipelines. Just talking.

### Three ways to deploy

| Mode | You say | What happens |
|---|---|---|
| **Git repo** | "despliega github.com/user/repo" | Clones, detects stack, deploys |
| **Docker Compose** | "despliega este compose" (sends file) | Reads it, starts containers |
| **AI Generate** | "hazme una tool de colores" | Claude Code writes everything, then deploys |

All three produce the same result: containers running behind Traefik with a staging URL.

## The 4 doors

Same agent, same workspace, same containers. Four ways in:

### 1. Telegram (from anywhere)
```
You: "qué tal las visitas de mi landing?"
Pleng: "42 visitors, 128 pageviews esta semana."

You: "el API va lento, qué pasa"
Pleng: [reads Docker logs, diagnoses] "El container está OOMKilled.
        Recomiendo añadir mem_limit: 512m al compose."

You: "reinicia reservas"
Pleng: "Reiniciado."
```
Quick commands from the subway. The agent resolves it alone.

### 2. Terminal (on the VPS)
```bash
make chat
# or: docker compose exec -it agent pleng chat

You: despliega github.com/user/my-api --name bookings
Pleng: Cloning... deploying... Live at http://a3f2.1.2.3.4.sslip.io
```
Full Claude Code experience. Diffs, files, logs. Iterate for hours.

### 3. Dashboard (read-only web panel)

`http://panel.YOUR-IP.sslip.io`

See all your sites, their status, URLs, Docker logs, and build history. Password-protected. The dashboard is **read-only** — all operations go through the agent.

### 4. Any external AI agent (skill.md)
```
# From Claude Code on your Mac:
You: "read http://panel.myserver.com/skill.md and deploy my project"

Claude Code: [reads skill.md, learns the API, deploys your code to the VPS]
```

The skill.md is auto-generated with the correct API URL for your instance. Any AI tool that can do HTTP can deploy to your Pleng. Authentication via API key (printed in logs on startup).

**External agents only deploy existing code** (git repo or upload). They don't generate projects — that's what the built-in agent does.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                      Your VPS                        │
│                                                      │
│  ┌──────────┐  ┌─────────────┐  ┌───────────────┐  │
│  │ Traefik  │  │ Platform    │  │    Agent       │  │
│  │ (proxy)  │  │ API         │  │ (Claude Code)  │  │
│  │ SSL/HTTP │  │ Docker sock │  │ pleng CLI      │  │
│  │ sslip.io │  │ SQLite      │  │ /projects vol  │  │
│  └──────────┘  └─────────────┘  └───────────────┘  │
│       ▲              ▲                  │            │
│       │         ┌────┘──────────────────┘            │
│       │         │  HTTP (internal network)            │
│  ┌──────────┐  ┌─────────────┐  ┌───────────────┐  │
│  │ Telegram │  │ Analytics   │  │  Dashboard    │  │
│  │ Bot      │  │ (tracking)  │  │  (React)      │  │
│  └──────────┘  └─────────────┘  └───────────────┘  │
│                                                      │
│  + your deployed apps (each in its own containers)   │
└─────────────────────────────────────────────────────┘
```

**6 containers. One `docker compose up`.**

| Container | Tech | Role |
|---|---|---|
| **traefik** | Traefik v3 | Reverse proxy. sslip.io staging, Let's Encrypt production |
| **platform-api** | FastAPI + SQLite | Orchestrates Docker. REST API. State. Auth. skill.md |
| **agent** | Claude Code + Flask | AI brain. Writes code + calls `pleng` CLI to deploy |
| **telegram-bot** | python-telegram-bot | Thin bridge: Telegram ↔ agent |
| **analytics** | FastAPI + SQLite | Pageview tracking. <1KB script. API-first |
| **dashboard** | React + nginx | Read-only web panel. Static files only |

### Key design decisions

- **Agent is isolated.** Shared `/projects` volume but NO Docker socket. Calls platform-api over HTTP. If the agent breaks, your infra keeps running.
- **sslip.io for staging.** `anything.YOUR-IP.sslip.io` resolves to your IP. No DNS config. Free. Instant.
- **Platform-api owns Docker.** Single point of control. All deploy/stop/restart goes through its REST API.
- **SQLite, not Postgres/MongoDB.** Zero extra containers. One file. Good enough for single-VPS scale.
- **API key auto-generated.** Created on first boot, printed to logs. Internal services fetch it automatically. External access requires the key.
- **Dashboard is read-only.** No deploy buttons. All operations via agent (Telegram/terminal). The dashboard is for monitoring, not control.

### Auth model

```
External (internet)  →  needs X-API-Key header
Internal (containers) →  no auth (Docker internal network)
Dashboard login      →  password (WEB_UI_PASSWORD) → returns API key
skill.md             →  public (documents the API, tells agents to use the key)
```

## Configuration

### Required

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | For Claude Code (the AI agent) |
| `TELEGRAM_BOT_TOKEN` | From @BotFather |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID |
| `PUBLIC_IP` | Your VPS public IP (`curl ifconfig.me` to find it) |

### Optional

| Variable | Default | Description |
|---|---|---|
| `BASE_DOMAIN` | — | Custom domain for the panel (enables HTTPS for panel) |
| `ACME_EMAIL` | admin@example.com | Email for Let's Encrypt certificates |
| `MODEL_NAME` | claude-sonnet-4-20250514 | Claude model for the agent |
| `GITHUB_TOKEN` | — | For deploying from private repos |
| `WEB_UI_PASSWORD` | admin | Dashboard login password |

## The `pleng` CLI

Inside the agent container, Claude Code has a `pleng` CLI tool that talks to platform-api:

```bash
pleng sites                              # List all sites
pleng deploy /projects/app --name app    # Deploy from path
pleng deploy-git https://github.com/... --name app  # Deploy from git
pleng logs my-app                        # Docker logs
pleng status my-app                      # Container status
pleng stop my-app                        # Stop
pleng restart my-app                     # Restart
pleng remove my-app                      # Remove (containers + files)
pleng promote my-app --domain x.com      # Staging → production + SSL
pleng chat                               # Interactive terminal mode
```

Claude Code decides which commands to run based on what you ask in natural language.

## External agent integration (skill.md)

Any AI agent that can read HTTP and make API calls can deploy to your Pleng:

```bash
# From your local Claude Code:
curl http://panel.YOUR-IP.sslip.io/skill.md
```

The skill.md documents all endpoints:

```
POST /api/deploy/git      — deploy from git repo
POST /api/deploy/upload   — deploy by uploading a tar.gz
GET  /api/sites           — list sites
GET  /api/sites/{id}/logs — Docker logs
POST /api/sites/{id}/stop — stop
POST /api/sites/{id}/promote — staging → production
```

All endpoints require `X-API-Key` header (get the key from `docker compose logs platform-api`).

## Project structure

```
pleng/
├── docker-compose.yml           # THE PRODUCT — 6 services
├── .env.example                 # 4 required env vars
├── Makefile                     # up, down, logs, chat, ps
├── LICENSE                      # AGPL-3.0
│
├── platform-api/                # Docker orchestrator
│   ├── Dockerfile               # Multi-stage: docker:27-cli + python:3.12
│   ├── app.py                   # FastAPI — routes, auth, skill.md
│   ├── deployer.py              # Deploy engine — compose up, Traefik labels, promote
│   └── database.py              # SQLite — sites, logs, settings, API key
│
├── agent/                       # AI brain (isolated — no Docker socket)
│   ├── Dockerfile               # python + node + claude-code + pleng CLI
│   ├── server.py                # Flask HTTP — receives messages, runs Claude Code
│   ├── entrypoint.sh            # Copies CLAUDE.md to /projects
│   ├── workspace/CLAUDE.md      # System prompt — tells Claude Code about pleng CLI
│   └── tools/pleng.py           # CLI tool — deploy, logs, stop, promote, chat
│
├── telegram-bot/                # Thin bridge
│   ├── Dockerfile
│   └── bot.py                   # Telegram ↔ agent HTTP, /sites command
│
├── analytics/                   # Built-in tracking
│   ├── Dockerfile
│   ├── app.py                   # FastAPI — collector + stats API
│   └── static/t.js              # Tracking script (<1KB)
│
└── dashboard/                   # Read-only web panel
    ├── Dockerfile               # Multi-stage: node build + nginx
    ├── nginx.conf               # Static files only (API via Traefik)
    └── src/
        ├── App.tsx              # Login + sidebar + routes
        └── pages/
            ├── LoginPage.tsx    # Password → API key
            ├── Dashboard.tsx    # Sites overview (auto-refresh)
            ├── SitesPage.tsx    # Site cards grid
            └── SiteDetailPage.tsx  # Logs, build-log, promote
```

## Roadmap

### Phase 1: Core — Done
- [x] Platform API — deploy, stop, restart, remove, logs, promote
- [x] Traefik — sslip.io staging, Let's Encrypt production
- [x] Agent — Claude Code in container with `pleng` CLI
- [x] Telegram bot
- [x] Dashboard — read-only, password-protected
- [x] Analytics — built-in pageview tracking
- [x] skill.md — auto-generated, for external agents
- [x] Auth — API key auto-generated, internal/external split
- [x] Upload endpoint — deploy without git

### Phase 2: Operations
- [ ] Health checks — auto-restart crashed containers
- [ ] Telegram alerts — site down, disk full, OOM
- [ ] Resource monitoring — CPU/RAM/disk per container
- [ ] Weekly summary reports via Telegram

### Phase 3: CI/CD
- [ ] Git webhook — auto-deploy on push
- [ ] Rollback to previous version
- [ ] Zero-downtime deploys

### Phase 4: Scale
- [ ] Multi-server support
- [ ] Backup and restore
- [ ] Environment cloning (staging → prod)

## Comparison

| | Coolify | Dokploy | Railway | **Pleng** |
|---|---|---|---|---|
| Self-hosted | Yes | Yes | No | **Yes** |
| AI agent | No | No | No | **Yes** |
| Natural language | No | No | No | **Yes** |
| Telegram | No | No | No | **Yes** |
| skill.md for agents | No | No | No | **Yes** |
| Built-in analytics | No | No | No | **Yes** |
| Free staging URLs | No | No | Auto | **Auto (sslip.io)** |
| Setup | Complex | Medium | Cloud | **`docker compose up`** |
| Price | Free | Free | $5-20/mo | **Free** |
| License | AGPL-3.0 | Apache 2.0 | Closed | **AGPL-3.0** |

## License

AGPL-3.0 — same license as Coolify. Self-host freely. If you modify the code and offer it as a service, you must open-source your changes. See [LICENSE](LICENSE).

---

<p align="center">
  <strong>One VPS. One command. Deploy anything by talking to it.</strong>
</p>
