# Public status page — xyz deployer bot

> Handover doc. Describes the bot's status page: access, content, how it works, operations.
> For the full operational playbook, see `xyz-bot/deploy/OPS.md`.

---

## Access

| | URL |
|---|---|
| **HTML page** (humans) | **http://217.65.145.163:8080/** |
| **JSON** (monitoring / machine) | http://217.65.145.163:8080/status.json |

- Hosted on the **bot's VPS** (Hostinger, Ubuntu 24.04, IP `217.65.145.163`).
- **Plain HTTP** (port 8080), no HTTPS or domain yet — see [Roadmap](#roadmap).
- The page **auto-refreshes every 30s**.
- **Read-only and public**: no sensitive data (everything comes from the public Hyperliquid API).

---

## What the page shows

- **Status 🟢 ONLINE / 🔴 OFFLINE** — derived from the freshness of the bot's last cycle
  (online if a cycle happened less than ~3× the poll interval ago, i.e. < 60s).
- **Dex** being watched (`xyz`).
- **Markets watched** — number of monitored markets (≈ 93).
- **Last check** — time since the last cycle.
- **Errors (streak)** — current consecutive error count (0 = nominal).
- **Latest alerts** — table of the latest detected config changes (UTC time, type, market,
  old → new value). This is the public history of alerts sent to the channel.

## JSON format (`/status.json`)

```json
{
  "dex": "xyz",
  "up": true,
  "markets_count": 93,
  "consecutive_errors": 0,
  "started_at": "2026-06-21T18:55:36+00:00",
  "last_cycle_at": "2026-06-21T18:55:48+00:00",
  "last_cycle_age_sec": 1,
  "recent_events": [
    { "at": "...", "type": "oi_cap_change", "coin": "xyz:NVDA", "old": "5000000.0", "new": "10000000.0" }
  ]
}
```

| Field | Meaning |
|---|---|
| `up` | bot considered alive (heartbeat freshness) |
| `markets_count` | markets watched at the last cycle |
| `consecutive_errors` | consecutive errors (0 = healthy) |
| `started_at` | start of the current process |
| `last_cycle_at` / `last_cycle_age_sec` | timestamp / age of the last cycle |
| `recent_events` | last 20 detected events |

---

## How it works (architecture)

- **Separate service** from the bot: `xyz-bot-web` (systemd), distinct from the `xyz-bot` daemon.
  If the page goes down, the bot keeps alerting; if the bot restarts, the page stays up.
- It **reads** the bot's Postgres database through a **dedicated read-only role** (`xyzbot_ro`) —
  it *technically cannot* write. Reads are cached for ~3s.
- The daemon writes a **heartbeat** (table `bot_status`) every cycle: last pass, market count,
  errors. The page derives the status from it and reads the latest events.
- Implementation: `xyz-bot/src/web.py` (aiohttp). Sources in the (private) GitHub repo.

## Operations (reminder)

```bash
ssh root@217.65.145.163
systemctl status xyz-bot-web          # page status
systemctl restart xyz-bot-web         # restart
journalctl -u xyz-bot-web -f          # logs
```
Full details: `xyz-bot/deploy/OPS.md`.

---

## Roadmap

- **Domain + HTTPS**: when opening the page widely, point a domain at the IP and put **Caddy** in
  front (automatic HTTPS). The URL becomes `https://status.<domain>`.
- **Possible enrichments**: channel subscribe link, markets sitting at their OI cap, history charts.

## Limits / good to know
- The **IP may change** if the VPS is recreated → the URL would change (a fixed domain solves this).
- Port **8080**: if blocked by a cloud firewall, open it on the Hostinger side.
- No authentication: the page is **public by design** (status + alerts = public info).
