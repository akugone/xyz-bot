# Feedback Trade.xyz — Export de conversation

**Groupe Telegram :** Feedback Trade.xyz (id `5222077641`)
**Période :** 3 juin 2026 → 17 juin 2026
**Participants :** Martin | iExec – DevRel, Tom IExec, fb
**Exporté le :** 19 juin 2026
**Heures en UTC**

---

## Lundi 15 juin 2026

**08:49 — Martin :** gmgm
Dis moi, il y aura un tool ou feature que vous aimeriez voir build par la communauté?

**09:28 — fb :** gm

**09:40 — fb :** honnêtement on a peu d'intérêts à déléguer des choses à la commu

ceci dit les bonnes idées sont tjrs les bienvenues

il y a des sujets un peu quant qu'on explore encore. par exemple comment éviter que notre backstop liquidator soit dans le rouge. comment quantifier le risque cross margin, comment modéliser proprement l'ADL. je bosse dessus donc intéressé d'échanger

à titre perso je dig ce qu'on pourrait faire avec Hermes agent. genre un skill ou un mcp. je suis fan. en gestion de risque ou en recherche. par exemple ca m'intéresse d'automatiser la recherche de nouveaux marchés (ou categories d'actifs)... y a plein de petits dashboards qui ont pop sauf que j ai pas bookmark

voilà qq pistes

**09:40 — fb :** tu voudrais build qqchose ?

**09:57 — Martin :** Cool merci pour ton retour, j'étais en reflexion ayant un peu de temps pour dev des trucs

**13:06 — fb :** dacc! t as des idées ?

**13:06 — fb :** ou des envies

---

## Mardi 16 juin 2026

**12:42 — Martin :** J'étais en reflexion, un app IOS ou une extension chrome etc.. je réfléchis ☺️

**17:27 — fb :** nice!

**17:27 — fb :** https://x.com/0xjeff/status/2066886171192709420?s=46 @akugone 👀

**18:38 — fb :** _(en réponse)_ pardon c est ce tweet enfait https://x.com/teknium/status/2066923624167248133?s=46

---

## Mercredi 17 juin 2026

**08:45 — Martin :** Tiens, je me disais : je me suis fait liquider il y a deux jours un système de notifs pourrait être intéressant sur Telegram ou par mail même pour push des opportunités ou news, comme par exemple l'IPO de SpaceX

**09:12 — fb :** _(en réponse)_ hmm nice to have mais pas sur que tu trouves bcp d users avec. ca a deja ete fait non ?

**09:12 — fb :** un truc qui pourrait servir a bcp de monde c est un telegram qui ping les updates du deployer de xyz

**09:13 — fb :** des qu un OI est increased, qu'un marché passe d isolated à no cross ou à cross, changement de levier...

**09:14 — fb :** si ca te tente bien sur. il faut encore manuellement qu on préviennent les market makers parfois

**09:16 — Martin :** Yes why not
Vous avez un env de dev / test open ?

**09:19 — Martin :** _(en réponse)_ Ah, mais non, même pas besoin d'un env de dev. En fait, juste une app Telegram qui va récupérer la data et qui ping

**09:20 — fb :** oui c est des calls à l'api d'hyperliquid

**09:20 — fb :** avec une sorte de db pour pas ping 2 fois le meme message

**09:21 — fb :** le deployer c'est 0x88806a71D74ad0a510b350545C9aE490912F0888

**09:21 — fb :** sur mainnet

**09:22 — Martin :** Ok, cool, merci. Je vais checker ça vendredi aprem j'ai du temps

**09:24 — fb :** ok ok

**09:26 — fb :** a toi de voir mais perso pour build ca je pense a une petite db postgresql (je t en file une ) et une micro vm dans aws avec un systemd service et ssh pour deploy

**09:28 — Martin :** _(en réponse)_ Yes, je te ping vendredi

**11:30 — fb :** cool

**11:31 — fb :** ca me rappel que y a des gens qui snipe les OI increase

**11:31 — fb :** c etait le cas sur MRVL

**11:31 — fb :** la upper discovery bound etait hit pcq nvda avait annoncé un partenariat donc les gens ont snipé l'OI increase pour in

**11:31 — fb :** manuellement\*
