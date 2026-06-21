# OPS — operating the xyz-bot (production)

Cheat sheet of common commands. The bot runs as a systemd daemon on the Hostinger VPS.

| | |
|---|---|
| **Server** | Ubuntu 24.04 — `217.65.145.163` |
| **Login** | `ssh root@217.65.145.163` (SSH key only, password auth disabled) |
| **Services** | `xyz-bot` (daemon) + `xyz-bot-web` (status page) — systemd, `active` + `enabled` |
| **Status page** | http://217.65.145.163:8080/ (HTML) · `/status.json` (JSON) |
| **Code** | `/opt/xyz-bot` (venv `.venv`, secrets `.env`) |
| **Database** | local Postgres 16 — db `xyzbot`, user `xyzbot` |
| **Channel** | Telegram "XYZ Deployer Alerts" via `@tradexyz_alerts_bot` |

> Tip: everything below can be run **from your Mac** by prefixing with
> `ssh root@217.65.145.163 '<command>'`, or after connecting with `ssh root@217.65.145.163`.

---

## Service status

```bash
systemctl status xyz-bot          # overview (active? since when? PID)
systemctl is-active xyz-bot       # -> active / inactive / failed
systemctl is-enabled xyz-bot      # -> enabled (starts at boot)
```

## Start / stop / restart

```bash
systemctl start xyz-bot           # start
systemctl stop xyz-bot            # stop (SIGTERM -> graceful shutdown)
systemctl restart xyz-bot         # restart
```

> The systemd commands below also apply to the web service by replacing
> `xyz-bot` with **`xyz-bot-web`** (e.g. `systemctl status xyz-bot-web`, `journalctl -u xyz-bot-web -f`).

## Status page

```bash
curl -s http://217.65.145.163:8080/status.json   # machine-readable status
# HTML page: open http://217.65.145.163:8080/ in a browser
systemctl restart xyz-bot-web                     # restart the page
```

## Logs

```bash
journalctl -u xyz-bot -f                  # LIVE logs (Ctrl-C to quit)
journalctl -u xyz-bot -n 100              # last 100 lines
journalctl -u xyz-bot --since "10 min ago"
journalctl -u xyz-bot -p err              # errors only
journalctl -u xyz-bot -f | grep EVENT     # follow only emitted alerts
```
Log markers:
- `seed — baseline of N coins recorded`: first run (empty DB) → records state without alerting.
- `cycle ok — N coins, no change`: normal cycle, nothing to report.
- `EVENT …`: a detected change (sent to the channel).
- `heartbeat — alive…`: periodic liveness proof.
- `cycle failed (… consecutive), backing off`: transient error, the bot slows down then retries.

## Database

```bash
# number of watched markets and journaled events
sudo -u postgres psql -d xyzbot -c "SELECT count(*) FROM market_state;"
sudo -u postgres psql -d xyzbot -c "SELECT count(*) FROM events;"

# last 20 detected events
sudo -u postgres psql -d xyzbot -c \
  "SELECT created_at, event_type, coin, old_value, new_value, notified_at FROM events ORDER BY id DESC LIMIT 20;"

# events recorded but NOT notified (possible send failure)
sudo -u postgres psql -d xyzbot -c \
  "SELECT created_at, event_type, coin FROM events WHERE notified_at IS NULL ORDER BY id DESC;"
```

> Reset the baseline (force a clean re-seed on the next cycle):
> ```bash
> systemctl stop xyz-bot
> sudo -u postgres psql -d xyzbot -c "TRUNCATE market_state, dex_state, events;"
> systemctl start xyz-bot
> ```

## Update the code (after a commit / change)

From your **Mac**, at the `~/dev/xyz` root:
```bash
rsync -az --delete \
  --exclude .venv --exclude .env --exclude __pycache__ --exclude .pytest_cache \
  xyz-bot/ root@217.65.145.163:/opt/xyz-bot/
ssh root@217.65.145.163 'chown -R xyzbot:xyzbot /opt/xyz-bot && systemctl restart xyz-bot xyz-bot-web'
```
If dependencies changed (`requirements.txt`):
```bash
ssh root@217.65.145.163 '/opt/xyz-bot/.venv/bin/pip install -r /opt/xyz-bot/requirements.txt && systemctl restart xyz-bot xyz-bot-web'
```

## Change the config (.env)

```bash
ssh root@217.65.145.163 'nano /opt/xyz-bot/.env'    # edit
ssh root@217.65.145.163 'systemctl restart xyz-bot' # apply
```
Variables: `POLL_INTERVAL_SEC`, `DEX_NAME`, `PG_DSN`, `WEB_PG_DSN`, `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_CHAT_ID`, `TELEGRAM_ADMIN_CHAT_ID`, `TELEGRAM_DRY_RUN`, `API_DOWN_THRESHOLD`,
`ERROR_BACKOFF_MAX_SEC`, `HEARTBEAT_INTERVAL_SEC`, `WEB_HOST`, `WEB_PORT`.

## Check Telegram

```bash
# is the bot responding? (identity)
curl -s "https://api.telegram.org/bot<TOKEN>/getMe"
# go silent (log instead of send): set TELEGRAM_DRY_RUN=true in .env then restart
```

## Server health

```bash
systemctl status postgresql       # is the DB up?
df -h /                           # disk space
free -h                           # RAM
uptime                            # load / uptime
```

---

## Quick troubleshooting

| Symptom | Lead |
|---|---|
| `systemctl status` = `failed` | `journalctl -u xyz-bot -n 50` → usually invalid `.env` or Postgres down |
| No alert despite a change | check `journalctl … grep EVENT`; check `TELEGRAM_DRY_RUN`, token, chat_id |
| API errors looping | normal if the Hyperliquid API is down: backoff slows down and retries on its own; an "API down" ops alert is sent after `API_DOWN_THRESHOLD` consecutive errors |
| Service does not start at boot | `systemctl enable xyz-bot` |

## Security
- `.env` (token + DB password): **only** on the VPS, never committed. Permissions `600`.
- **Web page = read-only Postgres role** (`xyzbot_ro`, via `WEB_PG_DSN`): it can only read. The daemon keeps the read/write role `xyzbot`.
- systemd units **hardened** (`NoNewPrivileges`, `ProtectSystem`, `SystemCallFilter=@system-service`…).
- SSH auth: **key only** (password disabled via `/etc/ssh/sshd_config.d/00-disable-password.conf`).
- Compromised Telegram token → revoke it in BotFather (`/revoke`), update `.env`, then `systemctl restart`.
