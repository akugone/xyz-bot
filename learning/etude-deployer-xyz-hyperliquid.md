# Étude du « deployer » trade.xyz — actions consultables pour le bot de monitoring

**Contexte projet :** bot Telegram qui ping les changements de config du DEX xyz (cf. conversation Feedback Trade.xyz, 17 juin).
**Adresse étudiée :** `0x88806a71D74ad0a510b350545C9aE490912F0888`
**Date :** 19 juin 2026

---

## 1. Conclusion principale : ce n'est pas un smart contract à ABI

L'adresse `0x8880…0888` est le **deployer HIP-3 du DEX `xyz`** (trade.xyz) sur Hyperliquid — confirmé par la doc trade.xyz (table « HIP-3 Metadata »). trade.xyz est le premier déployeur sous HIP-3 et représente la grande majorité de l'Open Interest HIP-3 (equities, indices/ETF, commodities tokenisés).

Conséquence directe pour le projet : **il n'y a pas d'ABI Solidity à lire avec des `view functions`.** Le deployer ne pousse pas des transactions EVM décodables ; il signe des **actions L1 Hyperliquid** (`PerpDeployAction`) traitées par HyperCore. On ne « consulte » donc pas le contrat — on surveille deux choses :

1. **Les actions que le deployer *peut* exécuter** (la liste fermée ci-dessous) → ça définit l'univers des events possibles.
2. **L'état déployé résultant**, lu via l'**info API Hyperliquid** (`POST https://api.hyperliquid.xyz/info`) → c'est là qu'on détecte concrètement les changements, par diff entre deux snapshots.

C'est exactement ce que décrivait fb : *« des calls à l'API d'hyperliquid… avec une db pour pas ping 2 fois le même message »*. La DB sert à stocker le dernier snapshot et à ne notifier que sur le delta.

Note : il existe aussi un **Oracle Updater** distinct (`0x1234567890545d1Df9EE64B35Fdd16966e08aCEC`) qui pousse les prix oracle — à ignorer pour le monitoring (voir §3, bruit).

---

## 2. Actions disponibles du deployer (`PerpDeployAction`)

Liste exhaustive des variantes que le deployer xyz peut signer (source : doc Hyperliquid « HIP-3 deployer actions »). La colonne « Pinger ? » indique la pertinence pour le bot.

| Action | Ce qu'elle fait | Pinger ? |
|---|---|---|
| `registerAsset2` / `registerAsset` | Initialise le dex et/ou liste un nouvel actif (coin, szDecimals, prix oracle initial, marginTableId, mode de marge) | **Oui** — nouveau marché listé |
| `setOpenInterestCaps` | Modifie le plafond d'Open Interest notionnel par actif | **Oui (prioritaire)** — c'est l'« OI increase » |
| `setMarginModes` | Change le mode de marge d'un actif : `strictIsolated` ↔ `noCross` | **Oui** — le « isolated → no cross/cross » |
| `setMarginTableIds` | Réassigne la table de marge d'un actif (donc le levier max via les tiers) | **Oui** — « changement de levier » |
| `haltTrading` | Halte / reprend le trading d'un actif (`{coin, isHalted}`) | **Oui** — arrêt/reprise marché |
| `setFundingMultipliers` | Multiplicateur de funding par actif (0 à 10) | Optionnel — impact funding |
| `setFundingInterestRates` | Composante taux d'intérêt du funding (−0.01 à 0.01) | Optionnel — impact funding |
| `setGrowthModes` | Active/désactive le « growth mode » par actif (max 1×/30 j) | Optionnel — rare |
| `setFeeScale` | Échelle des fees du dex (max 1×/30 j) | Optionnel — rare |
| `setFeeRecipient` | Change l'adresse qui reçoit les fees | Faible — interne |
| `setSubDeployers` | Délègue des permissions d'action à d'autres adresses | Faible — gouvernance |
| `setPerpAnnotation` | Métadonnées d'un perp (catégorie, description, displayName, keywords) | Faible — cosmétique |
| `setOracle` | Met à jour le prix oracle/mark (≈ toutes les 3 s) | **Non** — bruit permanent, à exclure |

Les modes de marge possibles (champ `marginMode`) : `strictIsolated` (marge isolée non retirable), `noCross` (isolé seulement), `normal` (cross autorisé). Le levier max est borné à `[1, 50]` et structuré en *margin tiers* (jusqu'à 3 paliers : plus la position est grosse, plus le levier max baisse).

---

## 3. Mapping demande de fb → action → comment la détecter

| Event demandé par fb | Action L1 sous-jacente | Détection via l'info API (champ à diff) |
|---|---|---|
| **OI increased** | `setOpenInterestCaps` | `perpDexLimits.coinToOiCap` et `totalOiCap` ; aussi `perpDexs[].assetToStreamingOiCap` |
| **isolated → no cross / cross** | `setMarginModes` | `meta.universe[].marginMode` (`strictIsolated`/`noCross`) |
| **changement de levier** | `setMarginTableIds` (+ tables) | `meta.universe[].maxLeverage` et `meta.marginTables[]` |
| **nouveau marché** | `registerAsset(2)` | nouvelle entrée dans `meta.universe[]` |
| **halt / reprise** | `haltTrading` | à confirmer côté API (cf. §5 — point à vérifier) |

Principe du bot : snapshot périodique de l'état → comparaison avec le snapshot précédent en base → ping Telegram uniquement sur les champs qui ont changé. **Exclure `oraclePx`/`markPx` du diff** sinon ça pingue en continu (mise à jour toutes les ~3 s par l'oracle updater).

---

## 4. Endpoints de lecture à consulter (info API)

Tous en `POST https://api.hyperliquid.xyz/info`, header `Content-Type: application/json`, body JSON. Pour le dex xyz, passer `"dex": "xyz"`. Les coins sont préfixés (`xyz:NVDA`, `xyz:TSLA`, `xyz:XYZ100`…).

**Les deux endpoints cœur du bot :**

`perpDexLimits` — les plafonds, dont les OI caps (la donnée n°1 à surveiller) :
```json
{ "type": "perpDexLimits", "dex": "xyz" }
// → { "totalOiCap", "oiSzCapPerPerp", "maxTransferNtl", "coinToOiCap": [["NVDA","..."],...] }
```

`meta` — l'univers des marchés + tables de marge (levier max, mode de marge, growth mode par coin) :
```json
{ "type": "meta", "dex": "xyz" }
// → universe[]: { name, szDecimals, maxLeverage, marginTableId, marginMode, onlyIsolated, growthMode }
//   marginTables[]: paliers de levier
```

**Endpoints d'appoint :**

| Endpoint (`type`) | Donne | Usage |
|---|---|---|
| `metaAndAssetCtxs` (`dex:"xyz"`) | universe **+ contexte live** : `openInterest`, `markPx`, `oraclePx`, `funding`, `dayNtlVlm` | suivre l'OI réel vs le cap |
| `perpsAtOpenInterestCap` (`dex:"xyz"`) | liste des perps actuellement **collés à leur OI cap** | détecter la demande contenue (pré-« OI increase ») |
| `perpDexs` | tous les dexs : `deployer`, `oracleUpdater`, `feeRecipient`, `assetToStreamingOiCap`, `assetToFundingMultiplier` | vérifier l'identité deployer + caps streaming |
| `perpDexStatus` (`dex:"xyz"`) | `totalNetDeposit` du dex | santé globale |
| `allPerpMetas` | tous les univers + ctx en **un seul call** | snapshot complet économe |
| `perpAnnotation` / `perpCategories` / `perpConciseAnnotations` | catégories/métadonnées des perps | détecter nouveaux actifs taggés |
| `perpDeployAuctionStatus` | statut de l'enchère de déploiement (prix du gas) | contexte avant un nouveau listing |

---

## 5. Reco d'architecture pour le bot (cadrage avant vendredi)

Aligné avec ce que propose fb (Postgres + micro VM AWS + systemd + SSH) :

1. **Poll** toutes les N secondes (ex. 15–30 s) : `meta` + `perpDexLimits` (+ `metaAndAssetCtxs` si on veut l'OI temps réel) pour `dex:"xyz"`. Un seul `allPerpMetas` peut remplacer plusieurs calls.
2. **Snapshot en base** (Postgres) : pour chaque coin, stocker `maxLeverage`, `marginMode`, `oiCap`, `isListed`, etc., avec un hash de l'état structurel.
3. **Diff** vs snapshot précédent en ignorant les champs de prix (oracle/mark). Sur tout changement d'un champ structurel → événement.
4. **Ping Telegram** formaté (ex. « 🆕 OI cap NVDA : 5M → 10M », « ⚙️ TSLA passe en cross », « ⛔ AAPL halted »). La table d'events traités évite les doublons.
5. Optionnel : pousser aussi les coins listés dans `perpsAtOpenInterestCap` (signal « ça va sûrement être augmenté »).

**Points à vérifier avec fb / à creuser (non résolus par la doc seule) :**

- La détection d'un `haltTrading` via l'info API n'est pas explicite — confirmer le champ exposé (probablement un flag de statut ou `isDelisted` dans `universe`).
- Les **rate limits** de l'info API en mode polling rapproché (à valider pour la fréquence de poll).
- Lire les **actions du deployer directement** (et pas seulement l'état résultant) nécessiterait l'accès aux données de bloc Hyperliquid / un node — l'approche par diff d'état via l'API est plus simple et suffit aux events visés.

---

## Sources

- [HIP-3 deployer actions — Hyperliquid Docs](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/hip-3-deployer-actions)
- [Perpetuals info endpoint — Hyperliquid Docs](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals)
- [HIP-3: Builder-deployed perpetuals — Hyperliquid Docs](https://hyperliquid.gitbook.io/hyperliquid-docs/hyperliquid-improvement-proposals-hips/hip-3-builder-deployed-perpetuals)
- [XYZ Architecture — trade[XYZ] Docs](https://docs.trade.xyz/) (table HIP-3 Metadata : deployer + oracle updater)
