# Concepts & vocabulaire — Hyperliquid, HIP-3, trade.xyz, perps

> Doc de **référence pédagogique** : il agrège toutes les notions clarifiées en Q&A (HIP-3, deployer, marge, carnet d'ordres, liquidation, infra…) pour relecture au calme.
> Il **complète** sans les répéter : le SPEC (`xyz-deployer-bot-SPEC.md` = plan de build) et `questions-pour-fb.md` (= à demander à fb). Ici, on explique les *concepts*, pas le projet.

---

## 1. HIP-3 — le cadre qui ouvre les marchés

**HIP-3** = « Hyperliquid Improvement Proposal n°3 », activé sur le mainnet en octobre 2025.

L'idée : **HIP-3 n'est pas un marché, c'est le *système* qui permet à n'importe quelle équipe de créer son propre DEX de perps** sur Hyperliquid. Avant, Hyperliquid décidait seul des marchés (BTC, ETH…). Avec HIP-3, des « builders » externes déploient et opèrent leurs propres marchés.

Trois briques :

- **Le builder** : l'équipe qui veut lancer ses marchés (ex. trade.xyz).
- **Le stake** : pour avoir le droit de déployer, il faut immobiliser une grosse caution en **HYPE** (500 000 HYPE sur le mainnet). Filtre anti-spam + engagement.
- **Les responsabilités** : c'est le builder qui doit ensuite opérer son marché (oracle, liquidité, leviers, OI caps, règlement). Hyperliquid fournit l'infra (HyperCore, la couche L1 qui gère les carnets et le règlement on-chain).

**Un « dex »** = une instance déployée par un builder. `xyz` (trade.xyz) en est une — la plus grosse (~90 % de l'Open Interest HIP-3, sur actions/indices/commodities tokenisés). D'autres builders ont les leurs, mais pèsent peu.

---

## 2. Le deployer et ses actions

**Le deployer** = l'**adresse on-chain** à qui Hyperliquid a donné le droit d'opérer un dex. Pour `xyz`, c'est `0x88806a71D74ad0a510b350545C9aE490912F0888` (+ une adresse « oracle updater » distincte pour les prix).

Point clé : **ce n'est PAS un smart contract avec une ABI.** Le deployer signe des **actions L1** (`PerpDeployAction`) traitées par HyperCore. Analogie : **deployer = compte admin, actions = commandes admin.**

Les actions qui changent la config d'un marché (les plus utiles à suivre) :

- `registerAsset` — liste un nouvel actif
- `setOpenInterestCaps` — modifie le plafond d'OI
- `setMarginModes` — change le mode de marge (strictIsolated ↔ noCross)
- `setMarginTableIds` — change la table de marge (donc le levier)
- `haltTrading` — halte / reprend un marché
- `setFundingMultipliers`, `setFundingInterestRates` — règlent le funding
- `setOracle` — pousse le prix (~toutes les 3 s ; c'est du bruit, pas un « event »)

Comme on ne peut pas lire ces actions via une ABI, on **surveille l'état déployé via l'API et on diff** entre deux instantanés. (Détail technique dans le SPEC.)

---

## 3. Les paramètres d'un marché

### Open Interest (OI) & OI cap
- **OI** = la taille totale de toutes les positions ouvertes (non fermées) sur un marché. Mesure « combien d'argent est engagé ».
- **OI cap** = le **plafond maximal** d'OI que la plateforme autorise sur ce marché. « Cap » = plafond en anglais.
- Quand le cap est atteint : on ne peut plus **ouvrir** de position qui *augmenterait* l'OI (on peut toujours fermer). Ce n'est **pas** une pénurie de « stock » — un perp est synthétique, il n'y a aucune action réelle qui s'épuise. C'est juste un **plafond de risque** posé par le deployer.

### Mode de marge — *comment le collatéral est partagé*
- **Isolated** : la marge est cloisonnée à la position. Une liquidation ne coûte que la marge allouée.
  - `strictIsolated` : isolé **et** marge non retirable d'une position ouverte.
  - `noCross` : isolé uniquement.
- **Cross** (`normal`) : tout le solde du compte sert de collatéral commun. Efficace en capital, mais une mauvaise position peut tout emporter (cascade interne).
- Sur un marché neuf/volatil, le deployer reste **conservateur** (isolé, levier bas), puis desserre quand le marché mûrit.
- **Sens des transitions (confirmé par fb)** : un marché ne peut évoluer que vers **plus de souplesse**, dans l'ordre `strictIsolated → noCross → normal (cross)`. Jamais en arrière (on ne re-serre pas un marché vers l'isolé une fois ouvert au cross). C'est logique : on desserre quand le marché a gagné en maturité/liquidité.

### Levier & margin tables
- **Levier** = multiplicateur position/collatéral (ex. x10).
- Ce n'est pas un simple nombre : un marché pointe vers une **table de marge** (`marginTableId`) à **paliers** : plus la position est grosse, plus le levier max baisse. Ex. : 0–1 M$ → 10x, au-delà → 5x. Garde-fou de risque. Borné à 50x, ≤ 3 paliers.

### Funding & funding multiplier
- **Funding** = petit paiement périodique entre longs et shorts pour **coller le prix du perp au prix réel**. Si trop de longs (perp au-dessus du réel) → les longs paient les shorts, ce qui ramène le prix.
- **Funding multiplier** (0 à 10) = bouton qui règle l'**intensité** de ce rappel, par marché. Sur un actif « gappy » (action tokenisée 24/7 alors que l'action réelle ferme la nuit/week-end), un multiplier élevé tire plus fort le perp vers le réel.

---

## 4. Comment fonctionne un marché (les bases)

### Le carnet d'ordres (order book)
La liste de tous les ordres en attente :
- **Bids** = les **acheteurs** (« je veux bien acheter à 100.5 »).
- **Asks** = les **vendeurs** (« je vends à 101.0 »).
- **Spread** = l'écart entre le meilleur bid et le meilleur ask. Tant que personne ne le franchit, rien ne se passe.
- **Dernier prix** = le prix du dernier échange réalisé.
- Un **trade** se déclenche quand un acheteur accepte le prix d'un vendeur (ou l'inverse) : les deux ordres se « matchent ».

### Long vs short
- **Long** = tu achètes, tu paries à la **hausse** (achat 100 → revente 110 = +10).
- **Short** = tu vends à découvert (tu vends ce que tu n'as pas, pour racheter moins cher), tu paries à la **baisse** (vente 100 → rachat 90 = +10).
- **Règle d'or** : tout trade a **deux côtés**. Pour chaque long, il y a un short en face. Le nombre de longs = le nombre de shorts, toujours.

---

## 5. Liquidation, backstop & risque

### La liquidation = un ordre forcé
Ta position ne change que quand **tu** trades. Une liquidation, c'est le moteur qui passe **un ordre de marché à ta place** pour fermer ta position quand ta marge passe sous le seuil de maintenance.
- Un **short** se fait liquider quand le prix **monte** (le short perd à la hausse) ; un **long**, quand le prix **baisse**.
- Comme tout ordre, cette clôture forcée a besoin d'une **contrepartie** : en temps normal, ce sont les autres traders / market makers du carnet. Ta position est **fermée** ; la contrepartie ouvre **sa propre** position. Personne ne « reprend » ta position (sauf cas backstop ci-dessous).

### Le balayage du carnet (slippage)
Si l'ordre forcé est **gros**, il consomme le meilleur niveau, puis le suivant, puis le suivant — et **à chaque niveau avalé, le prix se déplace**. C'est le « balayage ». Plus l'OI autorisé est élevé → positions plus grosses → balayage plus violent → ça peut liquider d'autres traders = **cascade de liquidations**.

### Le backstop liquidator (vault HLP)
- C'est un **mécanisme automatique du protocole** (chez Hyperliquid, le vault **HLP**). Aucun humain ne décide.
- Il n'intervient que dans le cas **anormal** : quand le carnet est trop vide pour absorber la clôture forcée. Il sert alors de **contrepartie de dernier recours**.
- Dans ce cas précis, il **hérite** de l'exposition (le même côté que le liquidé) et peut finir « **dans le rouge** » si le prix continue dans la mauvaise direction. C'est l'inquiétude de fb.

### ADL (Auto-Deleveraging)
Quand même le backstop / fonds d'assurance ne suffit pas, la plateforme **réduit automatiquement les positions des traders gagnants** du côté opposé pour équilibrer les comptes. Dernier filet, mais désagréable pour ceux qui se font « dé-leverager ».

### Le market maker (MM)
- C'est l'acteur qui **peuple le carnet** : il pose en continu des bids **et** des asks autour du prix, et gagne le **spread**.
- Lors d'un balayage, ses bids se font remplir pendant que le prix s'effondre → il se retrouve **long, à perte**. D'où l'intérêt de **le prévenir** quand un paramètre change (levier, OI cap, marge) — c'est le cœur de l'utilité du bot.

---

## 6. Le cycle de l'OI cap & le « snipe »

1. **Remplissage** : l'OI grimpe vers le cap.
2. **Saturation** : le marché atteint son cap → les nouvelles entrées sont **bloquées** = demande contenue (pas une file d'attente : les ordres qui augmentent l'OI sont juste **refusés**).
3. **Cap relevé** : le deployer augmente le plafond (`setOpenInterestCaps`).
4. **Ruée** : ceux qui attendaient se précipitent. Comme on ne peut pas pré-poser d'ordre, des **bots tirent à la milliseconde** où la capacité se libère = « **sniper** ». Le prix bouge dans le sens de la demande contenue (haussier dans le cas MRVL après la news NVDA → ça pompe).

→ « Un marché collé à son cap » est donc un **signal avant-coureur** d'une hausse d'OI imminente. C'est la valeur « longueur d'avance » que peut apporter le bot.

---

## 7. Vocabulaire infra (la phrase de fb)

> « une petite db postgresql, une micro vm dans aws avec un systemd service et ssh pour deploy »

- **PostgreSQL** : base de données. Ici, pour stocker les snapshots de l'état du dex et éviter d'envoyer 2× la même alerte.
- **Micro VM AWS** : petite machine virtuelle Linux toujours allumée (ex. EC2 `t3.micro`) qui héberge le bot. « Micro » = petite et peu chère.
- **Daemon** : un programme qui **tourne en permanence en arrière-plan**, détaché de ta session (pas un script lancé à la main qui s'arrête quand tu fermes le terminal). Beaucoup de services système en sont (`sshd`, `systemd`…).
- **systemd service** : `systemd` est le **gestionnaire de services de Linux**. Déclarer le bot comme « systemd service » = il démarre tout seul au boot, tourne en continu (daemon), et **redémarre automatiquement s'il plante**. Idéal pour du 24/7.
- **SSH** : connexion sécurisée à distance vers la VM, pour pousser le code et gérer le service.

En résumé, le stack proposé : une VM AWS qui fait tourner le bot en **daemon systemd** (fiable, 24/7), une **Postgres** pour la mémoire anti-doublon, **SSH** pour déployer.

---

## 8. Mini-glossaire express

| Terme | En une phrase |
|---|---|
| **HIP-3** | Cadre qui laisse des tiers déployer leurs propres DEX de perps sur Hyperliquid. |
| **Dex (xyz)** | Une instance de marchés déployée par un builder ; `xyz` = celle de trade.xyz. |
| **Deployer** | Adresse admin qui opère le dex en signant des actions L1 (pas un contrat). |
| **Perp** | Contrat à terme synthétique sans expiration ; tu paries sur le prix, sans posséder l'actif. |
| **Open Interest (OI)** | Total des positions ouvertes sur un marché. |
| **OI cap** | Plafond de risque sur l'OI fixé par le deployer ; atteint = plus d'ouverture nette. |
| **Funding** | Paiement longs↔shorts qui colle le prix du perp au réel. |
| **Funding multiplier** | Bouton (0–10) qui règle la force du funding par marché. |
| **Isolated / cross** | Marge cloisonnée par position / marge partagée sur tout le compte. |
| **Levier / margin table** | Multiplicateur de position ; défini par paliers (plus gros = moins de levier). |
| **Bid / ask** | Ordre d'achat / ordre de vente en attente dans le carnet. |
| **Spread** | Écart entre meilleur bid et meilleur ask. |
| **Long / short** | Parier à la hausse (acheter) / à la baisse (vendre à découvert). |
| **Liquidation** | Fermeture forcée d'une position quand la marge est insuffisante. |
| **Balayage / slippage** | Un gros ordre consomme plusieurs niveaux du carnet → le prix se déplace. |
| **Backstop liquidator (HLP)** | Contrepartie automatique de dernier recours quand le carnet ne suit pas. |
| **ADL** | Réduction forcée des positions gagnantes quand le backstop ne suffit pas. |
| **Market maker (MM)** | Acteur qui pose bids+asks et gagne le spread ; à prévenir quand la config change. |
| **Snipe (OI cap)** | Entrer en premier (souvent via bots) dès qu'un cap est relevé. |
| **Daemon** | Programme qui tourne en continu en arrière-plan. |
| **systemd** | Gestionnaire de services Linux qui lance/relance les daemons. |
