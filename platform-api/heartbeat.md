# Pleng Heartbeat

Each section defines a check level. The agent runs the commands
and reports via Telegram ONLY if something is wrong.

## quick | 120m

Run: `pleng system` and `pleng docker-ps`

If everything is normal (all containers running, RAM <90%, disk <85%), respond ONLY with the single word: OK

If something is wrong, explain in 1-2 lines.

## deep | 240m

Run:
1. `pleng system`
2. `pleng docker-stats`
3. `pleng errors --minutes 60`
4. `pleng logs-summary`

If everything is normal, respond ONLY with: OK

If something is unusual (high resource usage, errors, containers restarting), give a 2-3 line summary.

## full | 1440m

Run: `pleng health-report`

This is the daily audit (every 24h). Always give a brief status report (5-10 lines max):
- System resources (disk, RAM, load)
- Container count and status
- Any errors or anomalies
- One line conclusion
