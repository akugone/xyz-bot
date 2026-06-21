# Deployment — xyz-bot on a VPS (Hostinger, Ubuntu)

Runbook to run the bot 24/7 as a systemd daemon. Target: Ubuntu 22.04/24.04 VPS.
All commands run **on the VPS** (as root over SSH) unless stated otherwise.

> Prerequisites: VPS provisioned, IP known, your SSH key added. From your Mac:
> `ssh root@<VPS_IP>`

---

## 1. System packages

```bash
apt update && apt -y upgrade
apt -y install python3 python3-venv python3-pip git postgresql rsync
```

## 2. PostgreSQL: roles + database

```bash
# read/write role used by the daemon
sudo -u postgres psql -c "CREATE USER xyzbot WITH PASSWORD 'CHANGE_ME_strong_pw';"
sudo -u postgres psql -c "CREATE DATABASE xyzbot OWNER xyzbot;"

# read-only role used by the status page (least privilege)
sudo -u postgres psql -d xyzbot <<'SQL'
CREATE USER xyzbot_ro WITH PASSWORD 'CHANGE_ME_ro_pw';
GRANT CONNECT ON DATABASE xyzbot TO xyzbot_ro;
GRANT USAGE ON SCHEMA public TO xyzbot_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO xyzbot_ro;
ALTER DEFAULT PRIVILEGES FOR ROLE xyzbot IN SCHEMA public GRANT SELECT ON TABLES TO xyzbot_ro;
SQL
```

## 3. Service user (no login)

```bash
useradd --system --home /opt/xyz-bot --shell /usr/sbin/nologin xyzbot
mkdir -p /opt/xyz-bot
```

## 4. Get the code (private repo)

**Option A — GitHub deploy key (recommended).** On the VPS:
```bash
ssh-keygen -t ed25519 -C "xyzbot-vps" -f /root/.ssh/id_ed25519 -N ""
cat /root/.ssh/id_ed25519.pub
```
Copy the printed key → GitHub → repo `akugone/xyz-bot` → **Settings › Deploy keys › Add deploy key** (read-only). Then:
```bash
git clone git@github.com:akugone/xyz-bot.git /opt/xyz-bot-src
ln -s /opt/xyz-bot-src/xyz-bot /opt/xyz-bot     # /opt/xyz-bot points at the app dir
```

**Option B — from your Mac (no GitHub key):**
```bash
# on the Mac, at the repo root
rsync -av --exclude .venv --exclude .env xyz-bot/ root@<IP>:/opt/xyz-bot/
```

## 5. Python environment

```bash
cd /opt/xyz-bot
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 6. `.env` file (secrets — never committed)

```bash
cat > /opt/xyz-bot/.env <<'EOF'
HL_API_URL=https://api.hyperliquid.xyz/info
DEX_NAME=xyz
POLL_INTERVAL_SEC=5
PG_DSN=postgresql://xyzbot:CHANGE_ME_strong_pw@localhost:5432/xyzbot
WEB_PG_DSN=postgresql://xyzbot_ro:CHANGE_ME_ro_pw@localhost:5432/xyzbot
TELEGRAM_BOT_TOKEN=<BotFather token>
TELEGRAM_CHAT_ID=<broadcast channel chat_id>
TELEGRAM_ADMIN_CHAT_ID=<private chat_id for ops alerts>
TELEGRAM_DRY_RUN=false
EOF
chmod 600 /opt/xyz-bot/.env
```

## 7. Permissions

```bash
chown -R xyzbot:xyzbot /opt/xyz-bot-src /opt/xyz-bot   # (or just /opt/xyz-bot for Option B)
```

## 8. systemd services

```bash
cp /opt/xyz-bot/deploy/xyz-bot.service /opt/xyz-bot/deploy/xyz-bot-web.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now xyz-bot xyz-bot-web
```

## 9. Verify

```bash
systemctl status xyz-bot xyz-bot-web --no-pager
journalctl -u xyz-bot -f                       # live logs: seed then cycles
curl -s http://<IP>:8080/status.json           # status page reachable?
```
Expected: `seed — baseline de N coins…` on the first cycle, then `cycle ok …`. The first real
config change on the dex will be posted to the Telegram channel.

---

## Update the bot (after a new commit)

```bash
git -C /opt/xyz-bot-src pull
/opt/xyz-bot/.venv/bin/pip install -r /opt/xyz-bot/requirements.txt   # if deps changed
systemctl restart xyz-bot xyz-bot-web
```
(Or, with Option B, `rsync` from the Mac then restart — see `OPS.md`.)

## Notes
- `Restart=always` + guardrail (`StartLimitBurst=10` / 300s, in the `[Unit]` section): restarts on
  its own, but stops if it loops on failure (e.g. invalid `.env`) — check `systemctl status`.
- The bot handles SIGTERM: `systemctl stop` closes DB + HTTP cleanly.
- Security: never commit `.env`. If the token leaks, revoke it via BotFather (`/revoke`).
