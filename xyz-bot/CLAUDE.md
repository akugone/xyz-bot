# CLAUDE.md — Contexte projet : Bot d'alertes « deployer xyz » (Hyperliquid HIP-3)

> Fichier de contexte lu automatiquement par Claude Code. Il condense le SPEC complet
> (`../xyz-deployer-bot-SPEC.md`) + les décisions tranchées avec fb. Si un détail manque,
> se référer au SPEC et à `../concepts-hyperliquid-xyz.md`.

## But du projet
Bot Telegram qui **notifie en quasi-temps-réel les changements de configuration** du DEX de perps `xyz` (trade.xyz) sur Hyperliquid. Lecture seule de l'API + diff d'état + ping Telegram. **Aucune** signature de transaction, **aucun** ordre de trading.

**Audience** : retail + groupes Telegram de la communauté (PAS les market makers, déjà équipés). Outil public. Cas d'usage phare : les traders « snipent » les hausses d'OI cap.

## Faits clés (confirmés)
- Deployer xyz : `0x88806a71D74ad0a510b350545C9aE490912F0888` (mainnet). Ce n'est **pas** un contrat EVM à ABI — le deployer signe des actions L1 ; on ne peut pas les lire directement.
- **Donc on poll l'état via l'info API REST et on diff entre deux snapshots.** Pas de WebSocket (confirmé fb).
- API : `POST https://api.hyperliquid.xyz/info`, `Content-Type: application/json`, paramètre `"dex": "xyz"`. Coins préfixés (`xyz:NVDA`…).
- **Sub-deployers : il en existe.** → on surveille par diff d'état (agnostique à l'adresse-auteur), pas besoin de lister les adresses.
- **Transitions de marge** : sens unique `strictIsolated → noCross → normal (cross)`, jamais en arrière. Le bot doit détecter le passage vers cross aussi.

## Le concept central : les snapshots
Le deployer n'expose aucun flux d'events. On détecte les changements en comparant l'état courant au précédent.
- **Snapshot** = photo figée de la config du dex à un instant T, par coin.
- **Champs suivis** (par coin) : `max_leverage`, `margin_mode`, `margin_table_id`, `oi_cap`, `is_listed`, `is_halted`, `funding_mult`, `growth_mode` ; + `total_oi_cap` au niveau dex.
- **Exclure `oraclePx`/`markPx`** du diff (maj toutes les ~3 s = bruit).
- **Persister en Postgres** (pas juste en mémoire) : pour diff, anti-doublon, et survie aux redémarrages.
- **Premier run** : pas de snapshot précédent → stocker la baseline en silence (seed), ne PAS tout pinger comme « nouveau ». Les alertes démarrent au 2e cycle.

## Boucle (daemon, PAS un cron)
```
loop toutes les N s (cible 2–5 s) :
  1. fetch  : POST /info  (meta, perpDexLimits [, metaAndAssetCtxs]) dex="xyz"
  2. normalize : snapshot par coin
  3. diff   : vs dernier snapshot en base (ignorer prix)
  4. si delta : event typé → ping Telegram (dedup_key anti-doublon)
  5. persister le nouveau snapshot
  6. sleep N s
```
Tourne en daemon sous **systemd** (`Restart=always`) sur une micro VM AWS (fournie par fb). Postgres fournie par fb.

## Endpoints à utiliser
- `perpDexLimits` (dex="xyz") → `totalOiCap`, `coinToOiCap` (les OI caps, donnée n°1).
- `meta` (dex="xyz") → `universe[]` : `name, maxLeverage, marginTableId, marginMode, onlyIsolated, growthMode` + `marginTables[]`.
- `metaAndAssetCtxs` (dex="xyz") → ctx live : `openInterest`, prix, funding (optionnel pour OI réel vs cap).
- `perpsAtOpenInterestCap` (dex="xyz") → perps collés au cap (signal pré-increase, optionnel).

## Mapping event → champ diffé
- OI cap → `perpDexLimits.coinToOiCap`, `totalOiCap`
- Mode de marge → `meta.universe[].marginMode` (capter aussi → `normal`/cross)
- Levier → `meta.universe[].maxLeverage` (+ `marginTables[]`)
- Nouveau marché → nouvelle entrée dans `meta.universe[]`
- Halt/reprise → **à confirmer en M1** (champ de statut côté API, sinon déduire de `isDelisted`/disparition de ctx)

## Stack & conventions
- Python 3.11+, `httpx` (async), `asyncpg` ou `psycopg`, `python-dotenv`.
- Config par variables d'env (voir `.env.example`). Secrets jamais commités.
- Code dans `src/`, schéma SQL dans `db/schema.sql`, unit systemd dans `deploy/`.
- Log structuré + heartbeat. Backoff sur erreur API. Respecter les rate limits (à valider).

## Milestones (état)
- **M0 Cadrage** : ✅ (events, audience, REST, sub-deployers tranchés). Reste : canal Telegram exact, latence, rate limits, accès DB/VM.
- **M1 Lecture** : ✅ client info API + snapshot lisible (93 coins) + tests (`tests/`, 8 verts). Hébergement cible tranché : **VPS Hostinger** (pas l'AWS de fb).
  - **Découverte M1 — marginMode** : le champ `marginMode` n'est présent dans `meta.universe[]` que pour les marchés isolés (`strictIsolated`/`noCross`, avec `onlyIsolated:true`). Pour un marché cross (`normal`), il est **absent**. → on normalise `absent → "normal"` dans `snapshot._margin_mode()` pour que le diff capte la transition vers cross.
  - **Découverte M1 — halt** : aucun champ de halt explicite dans `meta` ni `metaAndAssetCtxs`. Seul `isDelisted` existe (delisting permanent ≠ halt temporaire). Le flag `isHalted` n'apparaît probablement que quand un marché est halté (lecture défensive déjà en place). **À confirmer sur un vrai halt avant M2.**
- **M2 Diff** : ✅ moteur de diff `src/events.py` (events typés + `dedup_key` + seed silencieux), boucle daemon en mémoire (`run_loop`), 12 tests verts, validé en live. **Persistance Postgres : à brancher** (étape suivante — remplacer le `prev` en mémoire de `run_loop` par load/save snapshot en base).
- **M2-bis Persistance** : ✅ `src/db.py` (asyncpg) — load/save snapshot + `record_new_events` (`ON CONFLICT (dedup_key) DO NOTHING`, renvoie les inédits). `run_loop` charge la baseline depuis Postgres (seed seulement si base vide), persiste à chaque cycle. Fallback mémoire si `PG_DSN` absent. 5 tests d'intégration (25 au total), validé en live (baseline survit au redémarrage).
- **M3 Notifications** : ✅ `src/messages.py` (templates SPEC §7) + `src/telegram.py` (`TelegramNotifier`, dry-run intégré). `run_loop` envoie chaque event inédit puis `mark_notified`. 13 tests (38 au total). **Envoi réel validé** via bot `@tradexyz_alerts_bot` (token + chat_id dans `.env` local, non commité). Cible actuelle = chat privé de test ; à terme = canal de broadcast.
- **M4 Daemon & déploiement** : ✅ **déployé en prod** sur VPS Hostinger `217.65.145.163` (Ubuntu 24.04). Service systemd `xyz-bot` actif + enabled (boot), Postgres 16 locale (base `xyzbot`, user `xyzbot`), code dans `/opt/xyz-bot` (venv + `.env` chmod 600). Envoi réel Telegram actif. Mise à jour : `rsync` du dossier `xyz-bot/` puis `systemctl restart xyz-bot`. Logs : `journalctl -u xyz-bot -f`.
- **Page de statut publique** : ✅ service web séparé `src/web.py` (aiohttp, lecture seule Postgres) → `GET /` (HTML statut + dernières alertes, auto-refresh 30s) et `GET /status.json`. Heartbeat écrit en base par le daemon (`bot_status`) à chaque cycle ; up/down déduit de la fraîcheur. Service systemd `xyz-bot-web` (port 8080). En prod : http://217.65.145.163:8080/. Sécurité : rôle Postgres **read-only** dédié (`WEB_PG_DSN`, user `xyzbot_ro`), cache lecture 3 s, units systemd durcies (`SystemCallFilter=@system-service`, etc.). Pas de domaine/HTTPS pour l'instant (IP brute) ; Caddy à ajouter le jour d'un domaine.
- **M5 Durcissement** : ⏳ en cours. ✅ rate limits vérifiés (1200 poids/min/IP, 40/cycle → ~40% à 5s, plancher ~3s ; cf. `ROADMAP.md`). ✅ alerte **API down/recovered** sur transition (seuil `API_DOWN_THRESHOLD`, vers `TELEGRAM_ADMIN_CHAT_ID` = chat privé, pas le canal public). Reste : test sur un vrai changement de config, confirmation mécanisme halt. Suite détaillée dans `ROADMAP.md`.
- **M2 Persistance & diff** : schéma + normalisation + moteur de diff.
- **M3 Notifications** : Telegram Bot API + templates + dedup.
- **M4 Daemon & déploiement** : boucle async + systemd + SSH.
- **M5 Durcissement** : rate limits, reconnections, alerte si API down, tests.

## Démarrage rapide (dev)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # remplir les valeurs
python -m src.main     # M1 : doit fetch + afficher un snapshot du dex xyz
```
