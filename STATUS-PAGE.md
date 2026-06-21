# Page de statut publique — xyz deployer bot

> Doc de passation. Décrit la page de statut du bot : accès, contenu, fonctionnement,
> exploitation. Pour le pilotage opérationnel complet, voir `xyz-bot/deploy/OPS.md`.

---

## Accès

| | URL |
|---|---|
| **Page HTML** (humains) | **http://217.65.145.163:8080/** |
| **JSON** (monitoring / machine) | http://217.65.145.163:8080/status.json |

- Hébergée sur le **VPS du bot** (Hostinger, Ubuntu 24.04, IP `217.65.145.163`).
- **HTTP simple** (port 8080), pas de HTTPS ni de domaine pour l'instant — voir [Évolutions](#évolutions).
- La page **s'auto-rafraîchit toutes les 30 s**.
- **Lecture seule et publique** : aucune donnée sensible (tout vient de l'API publique Hyperliquid).

---

## Ce que la page affiche

- **Statut 🟢 ONLINE / 🔴 OFFLINE** — déduit de la fraîcheur du dernier cycle du bot
  (online si un cycle a eu lieu il y a moins de ~3× l'intervalle de poll, soit < 60 s).
- **Dex** surveillé (`xyz`).
- **Markets watched** — nombre de marchés suivis (≈ 93).
- **Last check** — temps écoulé depuis le dernier cycle.
- **Errors (streak)** — nombre d'erreurs consécutives en cours (0 = nominal).
- **Latest alerts** — table des derniers changements de config détectés (heure UTC, type,
  marché, ancienne → nouvelle valeur). C'est l'historique public des alertes envoyées au canal.

## Format JSON (`/status.json`)

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

| Champ | Sens |
|---|---|
| `up` | bot considéré vivant (fraîcheur du heartbeat) |
| `markets_count` | marchés suivis au dernier cycle |
| `consecutive_errors` | erreurs d'affilée (0 = sain) |
| `started_at` | démarrage du process courant |
| `last_cycle_at` / `last_cycle_age_sec` | date / ancienneté du dernier cycle |
| `recent_events` | 20 derniers events détectés |

---

## Comment ça marche (archi)

- **Service séparé** du bot : `xyz-bot-web` (systemd), distinct du daemon `xyz-bot`.
  Si la page tombe, le bot continue d'alerter ; si le bot redémarre, la page reste debout.
- Il **lit en seule lecture** la base Postgres du bot, via un **rôle read-only dédié**
  (`xyzbot_ro`) — il ne *peut techniquement pas* écrire. Lectures mises en cache ~3 s.
- Le daemon écrit un **heartbeat** (table `bot_status`) à chaque cycle : dernier passage,
  nombre de marchés, erreurs. La page en déduit l'état et lit les derniers events.
- Implémentation : `xyz-bot/src/web.py` (aiohttp). Sources publiques sur le repo GitHub privé.

## Exploitation (rappel)

```bash
ssh root@217.65.145.163
systemctl status xyz-bot-web          # état de la page
systemctl restart xyz-bot-web         # redémarrer
journalctl -u xyz-bot-web -f          # logs
```
Détails complets : `xyz-bot/deploy/OPS.md`.

---

## Évolutions

- **Domaine + HTTPS** : quand on ouvre la page largement, pointer un nom de domaine sur
  l'IP et mettre **Caddy** devant (HTTPS automatique). L'URL deviendra `https://status.<domaine>`.
- **Enrichissements possibles** : lien d'abonnement au canal Telegram, marchés collés à leur
  OI cap, graphes d'historique.

## Limites / à savoir
- L'**IP peut changer** si le VPS est recréé → l'URL changerait (un domaine fixe règle ça).
- Port **8080** : s'il était fermé par un pare-feu cloud, l'ouvrir côté Hostinger.
- Pas d'authentification : la page est **publique par conception** (statut + alertes = infos publiques).
