# OPS — exploitation du bot xyz-bot (prod)

Aide-mémoire des commandes courantes. Le bot tourne en daemon systemd sur le VPS Hostinger.

| | |
|---|---|
| **Serveur** | Ubuntu 24.04 — `217.65.145.163` |
| **Connexion** | `ssh root@217.65.145.163` (clé SSH uniquement, mot de passe désactivé) |
| **Service** | `xyz-bot` (systemd) — `active` + `enabled` (démarre au boot) |
| **Code** | `/opt/xyz-bot` (venv `.venv`, secrets `.env`) |
| **Base** | Postgres 16 locale — base `xyzbot`, user `xyzbot` |
| **Canal** | Telegram « XYZ Deployer Alerts » via `@tradexyz_alerts_bot` |

> Astuce : tout ce qui suit peut se lancer **depuis ton Mac** en préfixant par
> `ssh root@217.65.145.163 '<commande>'`, ou en te connectant d'abord avec `ssh root@217.65.145.163`.

---

## État du service

```bash
systemctl status xyz-bot          # vue d'ensemble (actif ? depuis quand ? PID)
systemctl is-active xyz-bot       # -> active / inactive / failed
systemctl is-enabled xyz-bot      # -> enabled (démarre au boot)
```

## Démarrer / arrêter / redémarrer

```bash
systemctl start xyz-bot           # démarrer
systemctl stop xyz-bot            # arrêter (SIGTERM -> arrêt propre)
systemctl restart xyz-bot         # redémarrer
systemctl reload-or-restart xyz-bot
```

## Logs

```bash
journalctl -u xyz-bot -f                  # logs EN DIRECT (Ctrl-C pour quitter)
journalctl -u xyz-bot -n 100              # 100 dernières lignes
journalctl -u xyz-bot --since "10 min ago"
journalctl -u xyz-bot -p err              # erreurs uniquement
journalctl -u xyz-bot -f | grep EVENT     # suivre seulement les alertes émises
```
Repères dans les logs :
- `seed — baseline de N coins…` : 1er run (aucune base) → mémorise sans alerter.
- `cycle ok — N coins, aucun changement` : cycle normal, RAS.
- `EVENT …` : un changement détecté (et envoyé au canal).
- `heartbeat — vivant…` : preuve de vie périodique.
- `cycle en erreur (… consécutive[s]), backoff` : erreur transitoire, le bot ralentit puis réessaie.

## Base de données

```bash
# nombre de marchés suivis et d'events journalisés
sudo -u postgres psql -d xyzbot -c "SELECT count(*) FROM market_state;"
sudo -u postgres psql -d xyzbot -c "SELECT count(*) FROM events;"

# les 20 derniers events détectés
sudo -u postgres psql -d xyzbot -c \
  "SELECT created_at, event_type, coin, old_value, new_value, notified_at FROM events ORDER BY id DESC LIMIT 20;"

# events enregistrés mais NON notifiés (échec d'envoi éventuel)
sudo -u postgres psql -d xyzbot -c \
  "SELECT created_at, event_type, coin FROM events WHERE notified_at IS NULL ORDER BY id DESC;"
```

> Réinitialiser la baseline (forcer un re-seed propre au prochain cycle) :
> ```bash
> systemctl stop xyz-bot
> sudo -u postgres psql -d xyzbot -c "TRUNCATE market_state, dex_state, events;"
> systemctl start xyz-bot
> ```

## Mettre à jour le code (après un commit / une modif)

Depuis ton **Mac**, à la racine `~/dev/xyz` :
```bash
rsync -az --delete \
  --exclude .venv --exclude .env --exclude __pycache__ --exclude .pytest_cache \
  xyz-bot/ root@217.65.145.163:/opt/xyz-bot/
ssh root@217.65.145.163 'chown -R xyzbot:xyzbot /opt/xyz-bot && systemctl restart xyz-bot'
```
Si les dépendances ont changé (`requirements.txt`) :
```bash
ssh root@217.65.145.163 '/opt/xyz-bot/.venv/bin/pip install -r /opt/xyz-bot/requirements.txt && systemctl restart xyz-bot'
```

## Modifier la config (.env)

```bash
ssh root@217.65.145.163 'nano /opt/xyz-bot/.env'   # éditer
ssh root@217.65.145.163 'systemctl restart xyz-bot' # appliquer
```
Variables : `POLL_INTERVAL_SEC`, `DEX_NAME`, `PG_DSN`, `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_CHAT_ID`, `TELEGRAM_DRY_RUN`, `ERROR_BACKOFF_MAX_SEC`, `HEARTBEAT_INTERVAL_SEC`.

## Vérifier Telegram

```bash
# le bot répond-il ? (identité)
curl -s "https://api.telegram.org/bot<TOKEN>/getMe"
# basculer en mode silencieux (logs au lieu d'envoi) : mettre TELEGRAM_DRY_RUN=true dans .env puis restart
```

## Santé serveur

```bash
systemctl status postgresql       # la base tourne ?
df -h /                           # espace disque
free -h                           # RAM
uptime                            # charge / uptime
```

---

## Dépannage rapide

| Symptôme | Piste |
|---|---|
| `systemctl status` = `failed` | `journalctl -u xyz-bot -n 50` → souvent `.env` invalide ou Postgres down |
| Pas d'alerte alors qu'il y a eu un changement | vérifier `journalctl … grep EVENT` ; vérifier `TELEGRAM_DRY_RUN`, token, chat_id |
| Erreurs API en boucle | normal si l'API Hyperliquid est down : le backoff ralentit et réessaie seul |
| Le service ne démarre pas au boot | `systemctl enable xyz-bot` |

## Sécurité
- `.env` (token + mdp DB) : **uniquement** sur le VPS, jamais commité. Permissions `600`.
- Auth SSH : par **clé uniquement** (mot de passe désactivé via `/etc/ssh/sshd_config.d/00-disable-password.conf`).
- Mot de passe root du VPS : à régénérer depuis le dashboard Hostinger (il a transité en clair au setup).
- Token Telegram compromis → le régénérer dans BotFather (`/revoke`), puis mettre à jour `.env` + `systemctl restart`.
