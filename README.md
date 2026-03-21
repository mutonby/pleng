<p align="center">
  <h1 align="center">Pleng</h1>
  <p align="center"><strong>The first self-hosted, AI-native PaaS.</strong></p>
  <p align="center">
    Install on any VPS. Deploy apps by talking to an AI agent.<br/>
    Telegram, terminal, dashboard, or any external AI tool via skill.md.
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
# Edit .env: ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, PUBLIC_IP
docker compose up -d
```

Done. You now have:
- **Dashboard** at `http://panel.YOUR-IP.sslip.io`
- **Telegram bot** listening for commands
- **Terminal** via `make chat`
- **skill.md** at `http://panel.YOUR-IP.sslip.io/skill.md` for external agents

## How it works

You tell the agent what you want. It does the rest.

```
You: "hazme una API de reservas con Postgres"

Agent: writes code → creates Dockerfile → creates docker-compose.yml
       → deploys containers → configures Traefik → assigns subdomain

Agent: "Listo. Tu API: http://a3f2.178.63.85.114.sslip.io"

You: "ponle reservas.midominio.com"

Agent: updates Traefik → Let's Encrypt SSL → done

Agent: "Listo. https://reservas.midominio.com con SSL"
```

### The lifecycle

1. Everything starts as **staging** with a free sslip.io subdomain. No domain needed.
2. You can have 10 projects in staging with zero effort.
3. The ones you like, you **promote to production** with a custom domain + SSL.
4. The ones you don't, you stop or remove.
5. No git, no CI/CD, no pipelines. Just talking.

### Three ways to deploy

| Mode | You say | What happens |
|---|---|---|
| **Git repo** | "deploy github.com/user/repo" | Clones, detects stack, deploys |
| **Docker Compose** | "deploy this compose" (send file) | Reads it, starts containers |
| **AI Generate** | "build me a color converter tool" | Claude Code writes everything, then deploys |

## The 4 doors

Same agent, same workspace, same containers. Four ways to talk to it:

### 1. Terminal (on the VPS)
```bash
make chat
# or: docker compose exec -it agent pleng chat

You: deploy github.com/user/my-api --name bookings
Pleng: Cloning... deploying... Live at http://a3f2.1.2.3.4.sslip.io
```
Full Claude Code experience. See diffs, files, logs. Iterate for hours.

### 2. Telegram (from anywhere)
```
You: "qué tal las visitas de mi landing?"
Pleng: "42 visitors, 128 pageviews esta semana. Top page: /pricing"

You: "el API va lento, qué pasa"
Pleng: [reads Docker logs, diagnoses] "El container está al 95% de RAM.
        Recomiendo aumentar el límite en el compose."
```
Quick commands from the subway. The agent resolves it alone.

### 3. Dashboard (web)
`http://panel.YOUR-IP.sslip.io`

Visual overview: all sites, their status, URLs, logs, analytics. Deploy page with 3-mode selector. Promote staging to production with one click.

### 4. Any external AI agent (skill.md)
```
# From Claude Code on your Mac:
You: "read http://panel.myserver.com/skill.md and deploy my project"

Claude Code: [reads skill.md, learns the API, deploys your code to the VPS]
```

The skill.md is auto-generated with the correct API URLs for your instance. Any AI tool that can do HTTP can deploy to your Pleng.

## Architecture

```
┌─────────────────────────────────────────────────┐
│                    Your VPS                      │
│                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │ Traefik  │  │ Platform │  │    Agent      │  │
│  │ (proxy)  │  │   API    │  │ (Claude Code) │  │
│  │ SSL/HTTP │  │ (Docker  │  │ + pleng CLI   │  │
│  │ routing  │  │  engine) │  │              │  │
│  └──────────┘  └──────────┘  └──────────────┘  │
│                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │ Telegram │  │Analytics │  │  Dashboard   │  │
│  │   Bot    │  │(tracking)│  │   (React)    │  │
│  └──────────┘  └──────────┘  └──────────────┘  │
│                                                  │
│  + your deployed apps (each = docker compose)    │
└─────────────────────────────────────────────────┘
```

**6 containers. One `docker compose up`. That's the entire product.**

| Container | Tech | What it does |
|---|---|---|
| **traefik** | Traefik v3 | Reverse proxy. sslip.io for staging, Let's Encrypt for production |
| **platform-api** | Python FastAPI + SQLite | Orchestrates Docker. REST API. Owns all state. Serves skill.md |
| **agent** | Claude Code + Flask | AI brain. Writes code, calls platform-api via `pleng` CLI |
| **telegram-bot** | python-telegram-bot | Bridges Telegram messages ↔ agent |
| **analytics** | Python FastAPI + SQLite | Pageview collector. <1KB tracking script. API-first |
| **dashboard** | React + nginx | Web UI. Proxies API calls to platform-api and analytics |

### Key design decisions

- **Agent is isolated.** It has a shared `/projects` volume but does NOT have Docker socket access. It calls platform-api over HTTP to deploy. If the agent breaks, your infra keeps running.
- **sslip.io for staging.** No DNS config needed. `anything.YOUR-IP.sslip.io` resolves to your IP. Free, instant.
- **Platform-api owns Docker.** Single point of control. Everything goes through its REST API.
- **SQLite, not Postgres/MongoDB.** Zero extra containers. Good enough for single-VPS scale.
- **Analytics is API-first.** Unlike Plausible CE, you can programmatically create tracked sites.

## Configuration

### Required

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | For Claude Code (the AI agent) |
| `TELEGRAM_BOT_TOKEN` | From @BotFather |
| `TELEGRAM_CHAT_ID` | Your chat ID |
| `PUBLIC_IP` | Your VPS public IP (for sslip.io subdomains) |

### Optional

| Variable | Default | Description |
|---|---|---|
| `BASE_DOMAIN` | — | Custom domain for the panel (enables HTTPS) |
| `ACME_EMAIL` | admin@example.com | Let's Encrypt email |
| `MODEL_NAME` | claude-sonnet-4-20250514 | Claude model |
| `GITHUB_TOKEN` | — | For private repo deploys |
| `WEB_UI_PASSWORD` | admin | Dashboard password |

## Project structure

```
pleng/
├── docker-compose.yml           # THE PRODUCT — 6 services
├── .env.example                 # 4 required vars
├── Makefile                     # up, down, logs, chat, ps
│
├── platform-api/                # Docker orchestrator
│   ├── app.py                   # FastAPI routes + skill.md
│   ├── deployer.py              # Docker deploy engine
│   └── database.py              # SQLite state
│
├── agent/                       # AI brain
│   ├── server.py                # HTTP server → Claude Code
│   ├── workspace/CLAUDE.md      # Agent system prompt
│   └── tools/pleng.py           # CLI: deploy, logs, stop, promote...
│
├── telegram-bot/
│   └── bot.py                   # Telegram ↔ agent bridge
│
├── analytics/
│   ├── app.py                   # Collector + stats API
│   └── static/t.js              # Tracking script (<1KB)
│
└── dashboard/
    ├── nginx.conf               # Reverse proxy to API services
    └── src/pages/               # Dashboard, Deploy, Sites, Detail
```

## Roadmap

### Phase 1: Core — Done
- [x] Platform API (Docker deploy engine)
- [x] Traefik + sslip.io staging + Let's Encrypt production
- [x] Agent container with Claude Code + pleng CLI
- [x] Telegram bot
- [x] Dashboard with deploy/sites/detail pages
- [x] Built-in analytics
- [x] skill.md for external agents
- [x] Staging → production promotion

### Phase 2: Operations
- [ ] Health checks + auto-restart crashed containers
- [ ] Telegram alerts (site down, disk full)
- [ ] Resource monitoring (CPU/RAM/disk per container)
- [ ] Weekly summary reports via Telegram

### Phase 3: CI/CD
- [ ] Git webhook for auto-deploy on push
- [ ] Rollback to previous version
- [ ] Zero-downtime deploys

### Phase 4: Scale
- [ ] Multi-server support
- [ ] Backup and restore
- [ ] Environment cloning (staging → prod)

## Why "Pleng"?

| | Coolify | Dokploy | Railway | **Pleng** |
|---|---|---|---|---|
| Self-hosted | Yes | Yes | No | **Yes** |
| AI agent | No | No | No | **Yes** |
| Natural language | No | No | No | **Yes** |
| Telegram | No | No | No | **Yes** |
| skill.md / MCP | No | Partial | No | **Yes** |
| Analytics built-in | No | No | No | **Yes** |
| Staging subdomains | Manual | Manual | Auto | **Auto (sslip.io)** |
| Setup | Complex | Medium | Cloud | **`docker compose up`** |
| Price | Free | Free | $5-20/mo | **Free** |

## License

MIT

---

<p align="center">
  <strong>One VPS. One command. Deploy anything by talking to it.</strong>
</p>
