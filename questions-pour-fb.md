# Questions à poser à fb avant de démarrer le bot deployer xyz

## ✅ Réponses reçues de fb

- **Transitions de marge** : un marché peut aller `strict → noCross` ou `noCross → cross`, **mais pas l'inverse** (sens unique, desserrement seulement). → le bot doit aussi détecter le passage vers cross.
- **WebSocket ?** Non → c'est du **REST polling**.
- **Audience** : pas les MM (ils ont déjà l'infra pour la notif). Cible = **retail** et **autres groupes Telegram** (type « mlm »…). Un bot tiers qui confirme avec une notif claire reste utile.
- **Sub-deployers** : **oui, il y en a.** → on surveille par diff d'état (agnostique à l'adresse), pas besoin de les lister.

**Restent à caler avec fb :** le canal Telegram exact + la latence visée + d'éventuels rate limits, et la logistique (accès Postgres / VM AWS).

---

## Le message court à envoyer dans le Telegram (copier-coller) — déjà envoyé, conservé pour archive

> Hello 👋 pour cadrer le bot deployer xyz, je pars sur ces events à pinger — tu valides / tu ajoutes ?
>
> • OI cap augmenté (par actif)
> • Changement de mode de marge (strictIsolated ↔ noCross)
> • Changement de levier max (margin table)
> • Nouveau marché listé
> • Halt / reprise d'un marché
>
> Optionnels : changement de funding multiplier, et alerte quand un perp est collé à son OI cap (signal pré-increase).
>
> Et quelques questions techniques :
> 1. Un marché peut-il repasser en *cross* (normal) en live, ou c'est figé au listing ? (l'action setMarginModes ne gère que strictIsolated/noCross)
> 2. Y a un flux WebSocket pour ces updates, ou c'est du REST polling only ?
> 3. Latence cible pour prévenir les MM (1s ? 10s ?), et des rate limits connus sur l'info API ?
> 4. Le canal Telegram destinataire : public, MM only, les deux ?
> 5. Toutes les actions de config du dex xyz passent bien par 0x8880…0888, ou il y a des sub-deployers (autres adresses) à surveiller aussi ?
> 6. Tu me files bien la Postgres + la VM AWS + les accès ?

---

## Détail / pourquoi chaque question (pour toi, pas à envoyer)

**Périmètre des events**
- Valider la liste des 5 events MVP évite de coder un diff sur des champs inutiles.
- Optionnels (funding multiplier, perps at OI cap) : à inclure seulement s'il les juge utiles.

**1. Cross en live ?** La doc dit que `setMarginModes` ne bascule qu'entre `strictIsolated` et `noCross` ; le mode `normal` (cross autorisé) n'est settable qu'à l'enregistrement du marché. Or fb a dit « isolated → no cross *ou à cross* ». Il faut savoir si un vrai passage en cross peut arriver en live (sinon on ne le détectera jamais et ce n'est pas grave, ou il faut une autre source).

**2. WebSocket vs REST.** C'est le facteur n°1 de réactivité. Si un WS pousse ces changements → détection instantanée. Sinon → polling court (2–5 s). Conditionne l'archi.

**3. Latence & rate limits.** La latence acceptable dimensionne la fréquence de poll ; les rate limits disent jusqu'où on peut descendre sans se faire throttle.

**4. Canal destinataire.** Public (valeur communauté, les « snipers » d'OI) vs canal MM privé (l'usage interne qu'il a décrit). Peut impliquer deux canaux et deux niveaux de verbosité.

**5. Sub-deployers.** Hyperliquid permet de déléguer des actions à d'autres adresses. Si la config du dex xyz peut être modifiée par d'autres comptes que `0x8880…0888`, surveiller la seule adresse deployer via l'état déployé reste valable (on diff l'état, pas l'auteur), mais c'est bon à savoir pour la source de vérité.

**6. Infra.** Il a proposé Postgres + micro VM AWS + systemd + SSH. Confirmer qu'il fournit bien l'accès, sinon prévoir une alternative.

---

## Note de cadrage (tranché, plus besoin de demander)

**Périmètre = dex xyz uniquement.** Comme la collab est avec trade.xyz, traquer les autres dex HIP-3 n'a pas de sens. Le filtre se fait par `dex="xyz"` dans l'API (pas par l'adresse deployer). Question retirée du message.
