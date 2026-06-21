# Spec & plan de dev — Bot d'alertes « deployer xyz » (Hyperliquid HIP-3)

> Document autoportant. Destiné à être collé tel quel dans un prompt agent : il contient tout le contexte, les specs techniques, les endpoints, le modèle de données et le plan de dev. Aucune connaissance préalable du projet n'est requise.

---

## 1. Contexte & objectif

**Origine.** Demande de l'équipe trade.xyz (contact « fb ») : un bot Telegram qui **notifie en temps quasi-réel les changements de configuration** du DEX de perps `xyz` déployé sur Hyperliquid.

**Audience cible (confirmée par fb).** Pas les market makers — ils ont déjà leur propre infra pour recevoir ces notifs. La cible est le **retail** et les **autres groupes Telegram** de la communauté (ex. groupes type « mlm »…). Un bot tiers qui **confirme avec une notif claire** a quand même de la valeur pour ce public. Positionnement : outil **public / retail-facing**, pas une alerte interne MM. Cas d'usage phare : les traders « snipent » les augmentations d'OI cap (ex. constaté sur MRVL après une annonce de partenariat NVDA).

**Objectif.** Un service qui poll l'API Hyperliquid, détecte les changements d'état du dex `xyz`, et envoie un message Telegram formaté **une seule fois par changement** (pas de doublon).

**Ce que le projet N'EST PAS.** Pas de lecture de smart contract EVM, pas de signature de transactions, pas d'ordre de trading. Lecture seule (`POST /info`) + notification.

---

## 2. Faits techniques confirmés (sourcés)

- L'adresse `0x88806a71D74ad0a510b350545C9aE490912F0888` est le **deployer HIP-3 du dex `xyz`** (trade.xyz), sur le **mainnet** Hyperliquid. Confirmé par la doc trade.xyz (table « HIP-3 Metadata »).
- Oracle Updater (adresse distincte, à ignorer pour le monitoring) : `0x1234567890545d1Df9EE64B35Fdd16966e08aCEC`.
- **Le deployer n'est pas un contrat Solidity à ABI.** Il signe des **actions L1** (`PerpDeployAction`) traitées par HyperCore. On ne lit pas des `view functions` ; on **poll l'état déployé via l'info API et on diff** entre deux snapshots pour détecter les changements.
- Nom du dex dans l'API : `dex = "xyz"`. Les coins sont préfixés : `xyz:NVDA`, `xyz:TSLA`, `xyz:XYZ100`, etc.
- Endpoint REST de base : `POST https://api.hyperliquid.xyz/info`, header `Content-Type: application/json`.

**Sources :**
- HIP-3 deployer actions : https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/hip-3-deployer-actions
- Perpetuals info endpoint : https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals
- HIP-3 (overview) : https://hyperliquid.gitbook.io/hyperliquid-docs/hyperliquid-improvement-proposals-hips/hip-3-builder-deployed-perpetuals
- trade.xyz architecture (metadata deployer/oracle) : https://docs.trade.xyz/

---

## 3. Actions du deployer (`PerpDeployAction`) — référence

Liste fermée des actions que le deployer peut signer. La colonne « Tracker » = MVP par défaut (à faire valider par fb).

| Action | Effet | Tracker |
|---|---|---|
| `registerAsset2` / `registerAsset` | Init dex / liste un nouvel actif (coin, szDecimals, oraclePx, marginTableId, marginMode) | ✅ nouveau marché |
| `setOpenInterestCaps` | Modifie le plafond d'OI notionnel par actif | ✅ **prioritaire** (l'« OI increase ») |
| `setMarginModes` | change le mode de marge — transitions **sens unique** : `strictIsolated → noCross → normal (cross)`, jamais l'inverse (confirmé fb) | ✅ |
| `setMarginTableIds` | `Array<[coin, marginTableId]>` — réassigne la table de marge (→ levier max) | ✅ levier |
| `haltTrading` | `{coin, isHalted}` — halte/reprend un marché | ✅ |
| `setFundingMultipliers` | `Array<[coin, mult]>` (0–10) | ⚙️ optionnel |
| `setFundingInterestRates` | `Array<[coin, rate]>` (−0.01..0.01) | ⚙️ optionnel |
| `setGrowthModes` | `Array<[coin, bool]>` (max 1×/30j) | ⚙️ optionnel |
| `setFeeScale` | échelle de fees (max 1×/30j) | ❌ |
| `setFeeRecipient` | adresse réceptrice des fees | ❌ |
| `setSubDeployers` | délègue des permissions d'action à d'autres adresses | ❌ (sauf gouvernance) |
| `setPerpAnnotation` | métadonnées (catégorie, description, displayName, keywords) | ❌ cosmétique |
| `setOracle` | maj prix oracle/mark (~toutes les 3s) | ❌ **bruit — exclure du diff** |

Modes de marge : `strictIsolated` (marge isolée non retirable), `noCross` (isolé uniquement), `normal` (cross autorisé). **Transitions confirmées par fb : un marché ne va que dans le sens du desserrement — `strictIsolated → noCross → normal (cross)`, jamais en arrière.** Le bot doit donc détecter aussi le passage vers `normal` (cross), pas seulement strict↔noCross. Comme on diffe le champ d'état `marginMode` (qui prend n'importe quelle valeur), la détection est robuste quel que soit le mécanisme exact côté action. Levier max ∈ [1, 50], structuré en *margin tiers* (≤ 3 paliers, levier décroissant avec la taille de position).

**Sub-deployers (confirmé par fb) :** il existe des sub-deployers — d'autres adresses que `0x8880…0888` peuvent modifier la config du dex. Implication : **surveiller par diff d'état (et non par adresse-auteur) reste la bonne approche**, car on capte le changement quelle que soit l'adresse qui l'a signé. Pas besoin d'énumérer les sub-deployers pour le monitoring.

---

## 4. Endpoints de lecture (info API) & mapping

Tous : `POST https://api.hyperliquid.xyz/info`, body JSON, `"dex": "xyz"` pour le dex cible.

### Endpoints cœur (à poll)

**`perpDexLimits`** — les plafonds, dont les OI caps (donnée n°1) :
```json
// requête
{ "type": "perpDexLimits", "dex": "xyz" }
// réponse
{ "totalOiCap": "...", "oiSzCapPerPerp": "...", "maxTransferNtl": "...",
  "coinToOiCap": [["xyz:NVDA","..."], ["xyz:TSLA","..."]] }
```

**`meta`** — univers des marchés + tables de marge :
```json
// requête
{ "type": "meta", "dex": "xyz" }
// réponse (extrait universe[])
{ "universe": [
    { "name":"xyz:NVDA", "szDecimals":3, "maxLeverage":10, "marginTableId":10,
      "onlyIsolated":true, "marginMode":"strictIsolated", "growthMode":"enabled",
      "lastGrowthModeChangeTime":"..." } ],
  "marginTables": [ [10, { "description":"...", "marginTiers":[ {"lowerBound":"0.0","maxLeverage":10} ] } ] ] }
```

### Endpoints d'appoint

| `type` | Donne | Usage |
|---|---|---|
| `metaAndAssetCtxs` (`dex`) | universe + ctx live : `openInterest`, `markPx`, `oraclePx`, `funding`, `dayNtlVlm` | OI réel vs cap |
| `perpsAtOpenInterestCap` (`dex`) | liste des perps collés à leur OI cap | signal pré-« OI increase » |
| `perpDexs` (pas de `dex`) | tous les dexs : `deployer`, `oracleUpdater`, `feeRecipient`, `assetToStreamingOiCap`, `assetToFundingMultiplier` | vérif identité + caps streaming |
| `perpDexStatus` (`dex`) | `totalNetDeposit` | santé globale |
| `allPerpMetas` | tous les univers + ctx en un call | snapshot complet économe |
| `perpAnnotation` / `perpCategories` / `perpConciseAnnotations` | métadonnées/catégories | nouveaux actifs taggés |

### Mapping event → action → champ à diff

| Event | Action L1 | Champ détecté |
|---|---|---|
| OI cap modifié | `setOpenInterestCaps` | `perpDexLimits.coinToOiCap`, `totalOiCap` |
| Mode de marge changé | `setMarginModes` | `meta.universe[].marginMode` (détecter aussi → `normal`/cross) |
| Levier max changé | `setMarginTableIds` | `meta.universe[].maxLeverage` + `meta.marginTables[]` |
| Nouveau marché | `registerAsset(2)` | nouvelle entrée dans `meta.universe[]` |
| Halt / reprise | `haltTrading` | **À VÉRIFIER** — champ de statut côté API (probablement un flag ; sinon déduire via disparition de ctx / `isDelisted`) |

---

## 5. Architecture

**Pattern : daemon long-running** (PAS un cron). Raisons : cron a une granularité ≥ 1 min (trop lent) et perd l'état entre exécutions (or on a besoin du snapshot précédent). Le process tourne en continu sous **systemd** (restart auto si crash).

```
┌─────────────────────────────────────────────┐
│  systemd service (micro VM AWS)              │
│                                              │
│   boucle toutes les N s (cible 2–5 s) :      │
│     1. fetch  : POST /info (meta, perpDexLimits, [metaAndAssetCtxs]) dex="xyz"
│     2. normalize : extraire les champs structurels par coin
│     3. diff   : vs dernier snapshot en base (IGNORER oraclePx/markPx)
│     4. si delta : composer message + INSERT event (idempotence) + envoyer Telegram
│     5. persister le nouveau snapshot
│     6. sleep N s                             │
└──────────────┬───────────────────────────────┘
               │
        PostgreSQL (fournie par fb)
               │
        Telegram Bot API (canal cible)
```

**REST polling confirmé par fb** : pas de flux WebSocket pour ces changements de config → l'archi est bien un **polling court**, pas de fallback WS à prévoir.

### Réactivité
Latence ≈ intervalle de poll. L'oracle se met à jour ~toutes les 3 s, donc un poll **2–5 s** donne du quasi-temps-réel pour les changements de config. Valider les **rate limits** de l'info API avant de descendre trop bas.

---

## 6. Modèle de données (PostgreSQL)

```sql
-- État courant par (dex, coin) : sert de base au diff
CREATE TABLE market_state (
  dex            TEXT NOT NULL,
  coin           TEXT NOT NULL,
  max_leverage   INT,
  margin_mode    TEXT,           -- strictIsolated | noCross | normal
  margin_table_id INT,
  oi_cap         NUMERIC,        -- notional cap (coinToOiCap)
  is_listed      BOOLEAN DEFAULT TRUE,
  is_halted      BOOLEAN,
  funding_mult   NUMERIC,
  growth_mode    BOOLEAN,
  updated_at     TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (dex, coin)
);

-- Limites globales du dex
CREATE TABLE dex_state (
  dex          TEXT PRIMARY KEY,
  total_oi_cap NUMERIC,
  updated_at   TIMESTAMPTZ DEFAULT now()
);

-- Journal des events détectés = idempotence anti-doublon
CREATE TABLE events (
  id          BIGSERIAL PRIMARY KEY,
  dex         TEXT NOT NULL,
  coin        TEXT,
  event_type  TEXT NOT NULL,    -- oi_cap_change | margin_mode_change | leverage_change | new_market | halt | ...
  old_value   TEXT,
  new_value   TEXT,
  dedup_key   TEXT UNIQUE,      -- ex: sha256(dex|coin|event_type|new_value) → INSERT ON CONFLICT DO NOTHING
  notified_at TIMESTAMPTZ,
  created_at  TIMESTAMPTZ DEFAULT now()
);
```

Logique anti-doublon : calculer `dedup_key` par event ; `INSERT ... ON CONFLICT (dedup_key) DO NOTHING` ; n'envoyer le Telegram que si l'insert a réellement créé une ligne.

---

## 7. Format des messages Telegram (proposition)

```
🟢 OI cap augmenté — xyz:NVDA
5,000,000 → 10,000,000 USDC
{timestamp UTC}

⚙️ Mode de marge — xyz:TSLA
noCross → normal (cross activé)

📈 Levier max — xyz:AAPL
10x → 20x

🆕 Nouveau marché listé — xyz:META
levier 10x · strictIsolated · OI cap 2,000,000

⛔ Trading halté — xyz:AMZN   /   ✅ Trading repris — xyz:AMZN
```
À confirmer avec fb : canal cible, niveau de détail, faut-il un message par coin ou un message groupé quand une action touche plusieurs coins.

---

## 8. Stack & déploiement

- **Langage** : Python 3.11+ (httpx + asyncio) ou Node 20 (fetch + setInterval). Au choix de l'implémenteur ; Python recommandé pour la simplicité du polling/async.
- **DB** : PostgreSQL (fournie par fb).
- **Hébergement** : micro VM AWS (fournie par fb), service **systemd** (`Restart=always`), déploiement via SSH.
- **Config via variables d'env** : `HL_API_URL`, `DEX_NAME=xyz`, `POLL_INTERVAL_SEC`, `PG_DSN`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
- **Secrets** : jamais en clair dans le repo ; `.env` non commité / secrets manager.
- **Observabilité** : log structuré + un heartbeat (ex. ping « still alive » quotidien ou métrique) pour savoir si le service tourne.

### Exemple de unit systemd
```ini
[Unit]
Description=xyz deployer alert bot
After=network-online.target

[Service]
ExecStart=/usr/bin/python3 /opt/xyz-bot/main.py
EnvironmentFile=/opt/xyz-bot/.env
Restart=always
RestartSec=5
User=xyzbot

[Install]
WantedBy=multi-user.target
```

---

## 9. Plan de développement (milestones)

1. **M0 — Cadrage** : ✅ events / audience / REST / sub-deployers tranchés avec fb (voir §10). Reste à régler : canal Telegram exact, latence cible, rate limits. Récupérer accès DB + VM.
2. **M1 — Lecture** : client info API ; fetch + parse `meta`, `perpDexLimits`, `metaAndAssetCtxs` pour `dex="xyz"`. Logguer un snapshot lisible.
3. **M2 — Persistance & diff** : schéma SQL ; normalisation par coin ; moteur de diff (en ignorant oracle/mark) qui produit une liste d'events typés.
4. **M3 — Notifications** : intégration Telegram Bot API ; templates de messages ; idempotence via `dedup_key`.
5. **M4 — Daemon & déploiement** : boucle async + backoff sur erreur API ; unit systemd ; déploiement SSH sur la VM ; logs + heartbeat.
6. **M5 — Durcissement** : gestion des rate limits, reconnections, alerte si l'API est down, tests sur un changement réel (ou simulé en injectant un faux snapshot précédent).
7. **M6 (option)** : extension multi-dex ; second canal Telegram ; couche « signal pré-OI-increase » plus riche.

---

## 10. Points tranchés (réponses de fb) & risques restants

**Tranché par fb :**
- **Transitions de marge** : sens unique `strictIsolated → noCross → normal (cross)`, jamais en arrière. → le bot détecte les passages vers cross aussi.
- **REST polling only** : pas de WebSocket pour ces changements → polling court, point final.
- **Audience** : retail + autres groupes Telegram (pas les MM, déjà équipés). Outil public.
- **Sub-deployers** : ils existent. → on surveille par **diff d'état** (agnostique à l'adresse-auteur), pas besoin de lister les sub-deployers.

**Risques / points encore ouverts (à lever avant M2) :**
- **Détection des halts** : champ API non confirmé (à vérifier en M1 sur des données réelles).
- **Rate limits** de l'info API en polling rapproché.
- **Canal Telegram** cible exact + latence visée (à finaliser avec fb).
