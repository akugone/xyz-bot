# Déploiement — xyz-bot sur VPS (Hostinger, Ubuntu)

Runbook pour faire tourner le bot 24/7 en daemon systemd. Cible : VPS Ubuntu 22.04/24.04.
Toutes les commandes sont à lancer **sur le VPS** (en root via SSH), sauf indication contraire.

> Prérequis : VPS provisionné, IP connue, ta clé SSH ajoutée. Depuis ton Mac :
> `ssh root@<IP_DU_VPS>`

---

## 1. Paquets système

```bash
apt update && apt -y upgrade
apt -y install python3 python3-venv python3-pip git postgresql
```

## 2. PostgreSQL : rôle + base

```bash
sudo -u postgres psql -c "CREATE USER xyzbot WITH PASSWORD 'CHANGE_MOI_mdp_solide';"
sudo -u postgres psql -c "CREATE DATABASE xyzbot OWNER xyzbot;"
```
→ DSN : `postgresql://xyzbot:CHANGE_MOI_mdp_solide@localhost:5432/xyzbot`

## 3. Utilisateur de service (sans login)

```bash
useradd --system --home /opt/xyz-bot --shell /usr/sbin/nologin xyzbot
```

## 4. Récupérer le code (repo privé)

**Option A — clé de déploiement GitHub (recommandé).** Sur le VPS :
```bash
ssh-keygen -t ed25519 -C "xyzbot-vps" -f /root/.ssh/id_ed25519 -N ""
cat /root/.ssh/id_ed25519.pub
```
Copie la clé affichée → GitHub → repo `akugone/xyz-bot` → **Settings › Deploy keys › Add deploy key** (lecture seule). Puis :
```bash
git clone git@github.com:akugone/xyz-bot.git /opt/xyz-bot-src
ln -s /opt/xyz-bot-src/xyz-bot /opt/xyz-bot     # /opt/xyz-bot pointe sur le dossier appli
```

**Option B — depuis ton Mac (sans clé GitHub) :**
```bash
# sur le Mac, à la racine du repo
rsync -av --exclude .venv --exclude .env xyz-bot/ root@<IP>:/opt/xyz-bot/
```

## 5. Environnement Python

```bash
cd /opt/xyz-bot
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 6. Fichier `.env` (secrets — jamais commité)

```bash
cat > /opt/xyz-bot/.env <<'EOF'
HL_API_URL=https://api.hyperliquid.xyz/info
DEX_NAME=xyz
POLL_INTERVAL_SEC=5
PG_DSN=postgresql://xyzbot:CHANGE_MOI_mdp_solide@localhost:5432/xyzbot
TELEGRAM_BOT_TOKEN=<le token BotFather>
TELEGRAM_CHAT_ID=<le chat_id du canal>
TELEGRAM_DRY_RUN=false
EOF
chmod 600 /opt/xyz-bot/.env
```

## 7. Droits

```bash
chown -R xyzbot:xyzbot /opt/xyz-bot-src /opt/xyz-bot   # (ou /opt/xyz-bot seul en option B)
```

## 8. Service systemd

```bash
cp /opt/xyz-bot/deploy/xyz-bot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now xyz-bot
```

## 9. Vérifier

```bash
systemctl status xyz-bot --no-pager
journalctl -u xyz-bot -f          # logs en direct : seed puis cycles
```
Attendu : `seed — baseline de N coins…` au 1er cycle, puis `cycle ok …`. Le 1er vrai
changement de config sur le dex partira dans le canal Telegram.

---

## Mettre à jour le bot (après un nouveau commit)

```bash
git -C /opt/xyz-bot-src pull
/opt/xyz-bot/.venv/bin/pip install -r /opt/xyz-bot/requirements.txt   # si deps changées
systemctl restart xyz-bot
```

## Commandes utiles

```bash
systemctl restart xyz-bot     # redémarrer
systemctl stop xyz-bot        # arrêter (SIGTERM → arrêt propre)
journalctl -u xyz-bot -n 100  # 100 dernières lignes
journalctl -u xyz-bot -p err  # erreurs seulement
```

## Notes
- `Restart=always` + garde-fou (`StartLimitBurst=10` / 300 s) : redémarre seul, mais
  s'arrête si ça boucle en échec (ex. `.env` invalide) — voir `systemctl status`.
- Le bot gère SIGTERM : `systemctl stop` ferme proprement DB + HTTP.
- Sécurité : ne jamais committer `.env`. Si le token a fuité, le régénérer via BotFather (`/revoke`).
