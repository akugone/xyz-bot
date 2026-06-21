# Roadmap — xyz deployer bot

> Feuille de route vivante. Mise à jour au fil de l'eau. Voir aussi `DEBRIEF-FB.md`
> (points à confirmer avec fb), `xyz-deployer-bot-SPEC.md` (spec), `xyz-bot/deploy/OPS.md`.
> Dernière mise à jour : **2026-06-21**.

---

## ✅ Fait

- **M1 — Lecture** : client info API Hyperliquid + snapshot par coin (93 marchés).
- **M2 — Diff + persistance** : moteur de diff (events typés, dedup), Postgres (seed silencieux, survie au restart).
- **M3 — Notifications** : envoi Telegram sur le canal de broadcast « XYZ Deployer Alerts » (messages en **anglais**).
- **M4 — Déploiement** : daemon durci (backoff, heartbeat, arrêt propre) en prod sur VPS Hostinger, systemd, 24/7.
- **Page de statut publique** : http://217.65.145.163:8080/ (rôle DB read-only, cache, units durcies).
- **Revue de code + sécu** : factorisation, dead code retiré, moindre privilège, durcissement SSH/systemd.
- **M5 (partiel)** : rate limits vérifiés (voir ci-dessous) ; alerte **API down/recovered** vers chat admin.

---

## 🔜 Court terme (prochaines étapes)

- [ ] **Configurer le chat admin** (`TELEGRAM_ADMIN_CHAT_ID`) pour recevoir les alertes ops, et **tester l'alerte API down** (ex. couper l'accès réseau et vérifier le message).
- [ ] **Test sur un vrai changement de config** du dex (ou simulé) → confirmer le flux bout-en-bout en conditions réelles.
- [ ] **Confirmer le mécanisme de halt avec fb** (champ API non observé — cf. `DEBRIEF-FB.md`).
- [ ] **Ouvrir le canal au public** (passer le canal Telegram en public) une fois validé.

## 🌍 Moyen terme

- [ ] **Domaine + HTTPS** sur la page de statut (Caddy, auto-TLS) → URL propre `https://status.<domaine>`.
- [ ] **Enrichir la page** : lien d'abonnement au canal, marchés collés à leur OI cap, mini-historique.
- [ ] **Régénérer le mot de passe root** du VPS (a transité en clair au setup).
- [ ] **Sauvegardes** : la base est reconstructible (re-seed), mais un dump quotidien `events` (audit) serait un plus.

## 🧪 Long terme / options (M6)

- [ ] **Signal pré-OI-increase** : réintroduire `perpsAtOpenInterestCap` / `metaAndAssetCtxs` (OI réel vs cap).
- [ ] **Multi-dex** : généraliser au-delà de `xyz` (le code filtre déjà par `dex`).
- [ ] **Funding multiplier** : alimenter `funding_mult` (via `perpDexs.assetToFundingMultiplier`) si jugé utile.
- [ ] **Second canal / verbosité** : canal MM vs public, ou filtrage par type d'event.

---

## 📊 Référence — rate limits API Hyperliquid (vérifié 2026-06-21)

- Limite **agrégée : 1200 de poids / minute / IP** (toutes requêtes REST confondues).
- `meta` et `perpDexLimits` = **20 de poids chacune** (défaut des requêtes `info`).
- **Notre conso** : 2 requêtes/cycle = 40/cycle.
  - poll **5 s** → 12 cycles/min → **480/min (~40 %)** ✅ marge confortable (réglage actuel).
  - poll **3 s** → 20 cycles/min → 800/min (~67 %) ✅ encore ok si on veut plus de réactivité.
  - poll **2 s** → 30 cycles/min → 1200/min (**100 % = ne pas faire**).
- **Conclusion** : 5 s est sûr ; **ne pas descendre sous ~3 s**. Le rate limit n'est pas un souci au réglage actuel.
- Source : https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits
