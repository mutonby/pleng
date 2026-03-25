<p align="center">
  <h1 align="center">Pleng</h1>
  <p align="center"><strong>Your AI Platform Engineer.</strong></p>
  <p align="center">
    One command. One VPS. You get your own cloud<br/>
    with an AI agent that deploys, monitors, and operates everything.
  </p>
  <p align="center"><em>Powered by Claude Code — running inside a Docker container, operating your infrastructure via natural language.</em></p>
</p>

<p align="center">
  <a href="https://github.com/mutonby/pleng/actions/workflows/ci.yml"><img src="https://github.com/mutonby/pleng/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPL--3.0-blue.svg" alt="License: AGPL-3.0"></a>
  <a href="https://github.com/mutonby/pleng/issues"><img src="https://img.shields.io/github/issues/mutonby/pleng" alt="Issues"></a>
  <a href="https://github.com/mutonby/pleng/stargazers"><img src="https://img.shields.io/github/stars/mutonby/pleng" alt="Stars"></a>
</p>

<p align="center">
  <a href="#what-you-get">What you get</a> · <a href="#quickstart">Quickstart</a> · <a href="#workflows">Workflows</a> · <a href="#how-to-talk-to-it">Talk to it</a> · <a href="#architecture">Architecture</a> · <a href="CONTRIBUTING.md">Contributing</a>
</p>

---

## One command. Your own cloud.

```bash
curl -fsSL https://raw.githubusercontent.com/mutonby/pleng/main/install.sh | sudo bash
```

That's it. Fresh Ubuntu VPS → Docker, Pleng, SSL, Telegram bot, AI agent — all configured and running. The installer asks for your tokens interactively and handles everything.

Or if you prefer doing it manually:

```bash
git clone https://github.com/mutonby/pleng && cd pleng
cp .env.example .env  # add your tokens
docker compose up -d
```

## What you get

Install Pleng on any VPS and you get all of this out of the box:

| What you'd normally install separately | Pleng gives you |
|---|---|
| **Coolify / Dokploy** — deploy apps, reverse proxy, SSL | Deploy anything via Telegram. Traefik + Let's Encrypt automatic. |
| **Uptime Kuma** — monitoring + alerts | Health checks every 10 min. Auto-restart. Telegram alerts. |
| **Datadog / Grafana** — observability, metrics, logs | Agent inspects CPU, RAM, disk, Docker stats, Traefik errors, container logs — all via natural language. |
| **PagerDuty / OpsGenie** — intelligent alerting | AI-powered heartbeat: the agent reviews your system every 30 min, 1h, and 2h at increasing depth. Reports anomalies to Telegram. |
| **OpenClaw / AI agent** — an AI that does things for you | Claude Code agent that writes code, deploys, diagnoses, operates. |

### Built for AI agents, not just humans

Coolify, Dokploy, Plausible — they're dashboards built for humans clicking buttons. They have no API that an AI agent can use. They don't understand natural language. They can't be operated programmatically.

**Pleng is designed from the ground up for AI agents.** Every operation is available through:
- Natural language (Telegram / terminal)
- REST API (for any agent or script)
- **skill.md** — a machine-readable instruction file that any AI agent can read and immediately know how to deploy, manage, and monitor your apps

This means you can connect **any AI agent** to your Pleng:

```bash
# OpenClaw, Claude Code, Cursor, Windsurf, any agent:
"read http://panel.YOUR-IP.sslip.io/skill.md and deploy my project"
```

The agent reads `skill.md`, learns the API, authenticates with the API key, and starts deploying. No plugins. No integrations. One URL.

All self-hosted. All in 6 containers. All operated by talking to it.

### What this replaces

Before Pleng, to self-host a few apps you'd need to:

1. Install Docker, configure networking
2. Set up Traefik or Nginx as reverse proxy
3. Configure Let's Encrypt for SSL
4. Deploy each app manually with docker compose
5. Set up monitoring (Uptime Kuma, Grafana)
6. Configure alerts (email, Slack, Telegram)
7. Handle DNS, domains, subdomains
8. Debug issues by reading logs manually
9. Restart crashed services manually

With Pleng, you skip all of that. You talk to the agent and it handles everything.

## Workflows

### 1. "I have code, deploy it"

You already have a project (built with Claude Code, Cursor, by hand, whatever). You just want it live.

```
You: "deploy github.com/user/my-app"
Pleng: Cloning... building... deploying...
       Live at http://a3f2.89.141.205.249.sslip.io
```

Or send a docker-compose.yml via Telegram. Or use the API from your local Claude Code.

### 2. "Build me something and deploy it"

You don't have code. You describe what you want. The agent writes everything and deploys.

```
You: "build me a booking API with Postgres and a simple frontend"
Pleng: [writes Node.js API, Dockerfile, docker-compose with Postgres]
       [deploys everything]
       Live at http://fe01.89.141.205.249.sslip.io
```

Want changes? Just say so:

```
You: "add email field to the bookings endpoint"
Pleng: [edits code, redeploys]
       Updated and live.
```

### 3. "Put it in production"

Your staging app is ready. Time for a real domain with HTTPS.

```
You: "put bookings.mydomain.com on my-app"
Pleng: [configures Traefik, Let's Encrypt generates SSL cert]
       Live at https://bookings.mydomain.com
```

Point your domain's DNS A record to your VPS IP. Pleng handles the rest.

### 4. "Something's wrong"

The agent monitors your sites. If something goes down, it tells you and tries to fix it.

```
Pleng (Telegram alert): 🔴 my-app is DOWN. Connection refused.
Pleng: 🔄 Auto-restarted my-app.
Pleng: 🟢 my-app is back UP.
```

Or you ask:

```
You: "why is my-app slow?"
Pleng: [reads Docker logs]
       Container OOMKilled — out of memory.
       Want me to increase the limit?
```

### 5. AI Heartbeat — your agent watches the server

Pleng includes a heartbeat system where the AI agent periodically reviews your entire server. It's configured in a single file (`heartbeat.md`) with three check levels:

| Level | Every | What it does |
|---|---|---|
| **Quick** | 30 min | Container status, RAM, disk, load — a quick glance. Silent if OK. |
| **Deep** | 60 min | Reads logs from every container, checks Traefik errors, analyzes resource usage. |
| **Full** | 120 min | Complete system audit. Everything above plus trends and recommendations. |

The heartbeat runs in your **same Telegram conversation** — the agent has full context of your chat, your deploys, and the system state. It's not a dumb uptime ping; it's an AI reading your logs and telling you what's wrong.

```
⚡ Heartbeat quick

Container pleng-my-app-web-1 is restarting in a loop.
Last log: "Error: ECONNREFUSED 127.0.0.1:5432"
→ The Postgres container is down. Run: pleng restart my-app
```

**Edit from Telegram.** The `heartbeat.md` file lives on a persistent volume. Tell the agent "edit heartbeat.md and add a MongoDB check to the full heartbeat" — it does it, and the change survives redeploys.

### 6. "Day-to-day operations"

```
You: "logs for my-app"              → Docker logs
You: "restart my-app"               → Done
You: "stop the demo"                → Stopped
You: "list my sites"                → All sites with URLs and status
You: "redeploy my-app"              → Rebuild + restart
You: "how's the server doing?"      → Full system status
```

### 7. "Connect any AI agent"

Any AI agent that can read a URL and make HTTP calls can operate your Pleng. No plugins, no integrations, no setup.

```
# From Claude Code on your Mac:
"read http://panel.myserver.com/skill.md and deploy this project"

# From OpenClaw:
"connect to my Pleng at http://panel.myserver.com/skill.md"

# From Cursor, Windsurf, any agent:
Same thing. Read the skill.md. Done.
```

The `skill.md` is auto-generated and always up to date with your server's IP, API URL, and all available operations. The agent reads it once and knows how to:
- Deploy from git or upload
- Check status and logs
- Stop, restart, redeploy
- Promote to production with SSL

One URL. That's the entire integration.

## How to talk to it

Same agent, four interfaces:

| Interface | Best for |
|---|---|
| **Telegram** | Quick commands from anywhere. Deploys, status checks, alerts. |
| **Terminal** | Deep work on the VPS. Full Claude Code experience. `make chat` |
| **Dashboard** | Visual overview. Sites, logs, status. `http://panel.IP.sslip.io` |
| **skill.md** | External AI agents. Your Claude Code at home deploys to your server. |

## Quickstart

### Prerequisites

- A VPS with Docker installed (any provider — Hetzner, DigitalOcean, Contabo)
- 2GB+ RAM
- Ports 80 and 443 open
- A Telegram bot token (free, from [@BotFather](https://t.me/BotFather))

### Install

```bash
git clone https://github.com/mutonby/pleng
cd pleng
cp .env.example .env
```

Edit `.env`:

```bash
TELEGRAM_BOT_TOKEN=123456:ABC...   # From @BotFather
TELEGRAM_CHAT_ID=123456789         # Your chat ID
PUBLIC_IP=89.141.205.249           # Your VPS IP (curl ifconfig.me)
ACME_EMAIL=you@example.com         # For SSL certificates
```

For Claude Code auth, either:
- **OAuth** (default): run `docker exec -it pleng-agent-1 sudo -u claude env HOME=/home/claude claude /login` after first start
- **API key**: add `CLAUDE_AUTH_MODE=api_key` and `ANTHROPIC_API_KEY=sk-ant-...` to `.env`

Start:

```bash
docker compose up -d
```

### What to do after install

1. Open `http://panel.YOUR-IP.sslip.io` — you should see the dashboard
2. Message your bot on Telegram: "hello"
3. If using OAuth, do the login step above
4. Try: "build me a simple landing page and deploy it"
5. Check the staging URL it gives you

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
│  │ Telegram │  │  Health     │  │  Dashboard    │  │
│  │ Bot      │  │  Monitor    │  │  (React)      │  │
│  └──────────┘  └─────────────┘  └───────────────┘  │
│                                                      │
│  + your deployed apps (each in its own containers)   │
└─────────────────────────────────────────────────────┘
```

| Container | What it does |
|---|---|
| **traefik** | Reverse proxy. Free staging URLs via sslip.io. HTTPS via Let's Encrypt for production. |
| **platform-api** | Orchestrates Docker. REST API. State in SQLite. Serves skill.md. Health monitoring. |
| **agent** | Claude Code with `pleng` CLI. Writes code, deploys, diagnoses. Isolated — no Docker socket. |
| **telegram-bot** | Bridges Telegram ↔ agent. Sends alerts for site health. |
| **dashboard** | React web panel. Sites, logs, status. Read-only — all operations via agent. |

### Key design decisions

- **Agent is sandboxed.** Claude Code runs inside a Docker container with no Docker socket, no host access, no sudo to the host. It can only affect infrastructure through the `pleng` CLI → platform-api HTTP calls. If the agent hallucinates or goes rogue, it can't break your server — it only has the tools you give it.
- **sslip.io for staging.** `anything.YOUR-IP.sslip.io` resolves to your IP. No DNS config needed. Free. Instant.
- **Platform-api owns Docker.** Single point of control for all container operations.
- **SQLite, not Postgres.** Zero extra containers. One file. Enough for single-VPS scale.
- **Health monitoring built in.** HTTP checks every 10 min + AI heartbeat at 3 depth levels. Auto-restart on failure. Telegram alerts.
- **Editable config from Telegram.** Both `CLAUDE.md` (agent instructions) and `heartbeat.md` (monitoring config) live on persistent volumes. Edit them from Telegram — changes survive redeploys.
- **Your docker-compose.yml is never modified.** Pleng generates its own overlay file for Traefik labels.

## The `pleng` CLI

Inside the agent, Claude Code has these tools:

```bash
# Deployment & management
pleng sites                              # List all sites
pleng deploy <path> --name <name>        # Deploy a project
pleng deploy-git <url> --name <name>     # Deploy from git
pleng redeploy <name>                    # Rebuild + restart
pleng logs <name>                        # Docker logs
pleng status <name>                      # Container info
pleng stop <name>                        # Stop
pleng restart <name>                     # Restart
pleng remove <name>                      # Remove
pleng promote <name> --domain <domain>   # Production + SSL

# Observability & diagnostics
pleng system                             # CPU, RAM, disk, load, uptime
pleng docker-ps                          # All containers on the host
pleng docker-stats                       # CPU + RAM per container
pleng errors [--minutes 60]              # Recent Traefik 5xx errors
pleng logs-summary                       # Recent errors from ALL sites
pleng health-report                      # Full system report (all of the above)
```

## Why not just use Coolify?

| | Coolify | Dokploy | Railway | **Pleng** |
|---|---|---|---|---|
| Self-hosted | Yes | Yes | No | **Yes** |
| AI agent | No | No | No | **Yes** |
| Natural language ops | No | No | No | **Yes** |
| Build apps from description | No | No | No | **Yes** |
| Telegram control | No | No | No | **Yes** |
| Auto-restart + alerts | Plugin | No | No | **Built-in** |
| AI-powered monitoring | No | No | No | **Yes — heartbeat.md** |
| System observability | Dashboard | Dashboard | Dashboard | **AI reads logs + metrics for you** |
| skill.md for agents | No | No | No | **Yes** |
| Free staging URLs | No | No | Auto | **Auto (sslip.io)** |
| Setup | Complex | Medium | Cloud | **`docker compose up`** |
| Price | Free | Free | $5-20/mo | **Free** |

Coolify is a great dashboard for deploying apps. Pleng is an AI agent that operates your entire server. Different tools for different workflows. If you want to click buttons, use Coolify. If you want to talk to your infra, use Pleng.

## Configuration

### Required

| Variable | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | From [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID |
| `PUBLIC_IP` | Your VPS public IP (`curl ifconfig.me`) |
| `ACME_EMAIL` | Email for Let's Encrypt SSL certificates |

### Optional

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | If using API key auth (instead of OAuth) |
| `CLAUDE_AUTH_MODE` | oauth | `oauth` or `api_key` |
| `MODEL_NAME` | claude-sonnet-4-20250514 | Claude model for the agent |
| `GITHUB_TOKEN` | — | For deploying from private repos |
| `WEB_UI_PASSWORD` | admin | Dashboard login password |

## Troubleshooting

**Bot not responding?**
- Check `docker compose logs telegram-bot` — is it polling?
- Verify `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`
- The bot only responds to the configured chat ID (security)

**Deploy failed?**
- Check `docker compose logs agent` for Claude Code errors
- Check the site's build log in the dashboard
- OAuth not configured? Run the login command (see Quickstart)

**HTTPS not working after promote?**
- Verify your domain's DNS A record points to your VPS IP
- Check `docker compose logs traefik` for Let's Encrypt errors
- `ACME_EMAIL` must be a real email (not example.com)

**Agent says "starting up"?**
- The agent waits for platform-api to be ready. Give it 30 seconds.

## License

AGPL-3.0 — same as Coolify. Self-host freely. If you modify the code and offer it as a service, you must open-source your changes. See [LICENSE](LICENSE).

---

<p align="center">
  <strong>One VPS. One command. Your own cloud with an AI that runs it.</strong>
</p>
