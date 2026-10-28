# O5 — Durcissement : clore les écarts du contrat personnel

*Spec de la session S6 du sprint 5 — 28/10/2026. Découpage : [`2026-10-28-sprint5-sessions.md`](2026-10-28-sprint5-sessions.md). Indépendante. Issue #156.*

## 1. Intention

Arriver au rendu du 15/11 avec un **contrat personnel cohérent et tenu** (K1 → K11), un dossier de conception à jour, et une **grille de retours** tenue sur toute la série d'ateliers (modalité d'évaluation du brief). C'est du travail de clôture, pas de nouvelle fonction.

## 2. Objectifs

| # | Écart | Ce qu'il faut produire | Source |
|---|---|---|---|
| 1 | **D-V9 — bilan incohérent** | `docs/contrat-personnel.md` : le tableau fait foi. Bilan corrigé : **7 tenus** (K3, K4, K5, K7, K8, K10, K11) · **4 en cours** (K1, K2, K6, K9) · **0 avenant** | recette-k-2026-10-27-staging.md |
| 2 | **K1 — dossier limite** | Le barème n'a pas de classe « limite » : jouer un dossier **hors barème** en staging et consigner le résultat attendu (revue humaine motivée) | contrat §5 |
| 3 | **K6 — tchat au clavier** | Revérifier « Tchat corpus » au clavier après le déploiement de #147 ; consigner | contrat §5 |
| 4 | **K2 — preuve sur les traces** | Par requête SQL (`GET /api/traces/{trace_id}`), puis en KQL **après S1** | contrat §5, S1 |
| 5 | **K9 — démo App Insights** | Application Map, Transaction Diagnostics, Live Metrics, KQL sur `audit.agent` : **après S1** | S1 |
| 6 | **Fusion de #145, #146, #147** | Fusionnées après la recette ; leurs délais (calcul 20 s, MCP 22 s, Actuaire 4 s) sont alors livrés | README |
| 7 | **D-V11 — P45 dans le dossier** | Reporter P45 dans le dossier (addendum V2.13 §10.1), au format section · texte actuel · texte corrigé | addendum V2.13 |
| 8 | **D-V12 — `evals-pr`** | Hors périmètre ; seulement cité comme limite connue dans `docs/exploitation.md` (S3) | README |
| 9 | **Grille de retours** | `docs/grille-retours.md` : un tableau par atelier (date, relecteur, retour, décision, issue ou PR, statut). Les retours des ateliers 1 à 4 sont repris des documents existants (`docs/demo-atelier*.md`, `Brief5/grille-atelier-2-socle-chaine.md`, …) ; l'atelier 5 est ajouté à sa date | brief §4.1 |
| 10 | **Commentaire de `make up`** | Le corriger : la cible lance déjà les 7 services | constat du 28/10 |

## 3. Non-objectifs

- Toute nouvelle fonction. Les corrections de bugs révélés par les ateliers passent chacune par sa propre issue, puis une PR.
- Réactiver `evals-pr` (U5).

## 4. Anti-objectifs

- Passer un K à « tenu » sans preuve consignée dans `eval/preuves/`.
- Réécrire l'historique des retours d'ateliers : la grille consigne ce qui a été dit et décidé, même ce qui a été refusé.

## 5. Contraintes

- **Grille de l'atelier 5** (`grille-atelier-5-vigie-demo.pdf`) : `🔴` non fournie le 28/10. Sans elle, la ligne « atelier 5 » de la grille reste à remplir pendant l'atelier.
- **Critères C5 et C6** (compétences transversales Simplon) : `🔴` absents de `Referentiel-Certification.pdf` ; l'auto-évaluation les laisse en `🔴`.
- Les points 4 et 5 attendent S1 en staging ; les points 6 et 2 attendent la fin du gel (après le 30/10).
- Le dossier à amender est `dossier-conception-v1.2.pdf` (confirmé par Acerola le 28/10).

## 6. Preuves de fin de session

- Bilan de `docs/contrat-personnel.md` cohérent avec son tableau ; chaque K « tenu » renvoie à une preuve.
- `eval/preuves/` : le dossier limite (K1), le tchat au clavier (K6), K2 en SQL et en KQL, K9.
- `docs/grille-retours.md` à jour.
- Les amendements du dossier (P45, et D42 → sprint 5 issu de S5) regroupés avec ceux de S4.

## 6 bis. Précisions issues de la relecture (28/10, *mes choix*)

- **Bilan** : le bilan D-V9 (7 tenus, 4 en cours) est écrit **tout de suite**. Il est ensuite recompté à chaque preuve consignée. Un K ne passe « tenu » que si une preuve existe dans `eval/preuves/`.
- **P45** : le texte est dans `certification/Brief5/dossier-conception-v1.2.pdf`, lisible. Le constructeur cite le texte actuel tel qu'il le lit.
- **Grille des ateliers 1 à 4** : on ne consigne que ce qui est écrit dans les sources. Si une décision ou un statut manque, la case porte « non consigné » ; on n'invente rien.
- **Dossier hors barème (K1)** : le constructeur **vérifie d'abord** le comportement réel. Le domaine lève déjà `DonneeHorsBareme`. Si le résultat n'est pas une revue humaine motivée, une issue est ouverte avant toute preuve.
- **Ordre** : fusion de #145, #146 et #147 **juste après la démo du 30/10**, avant S1. Les points 4 et 5 suivent S1 en staging.

## 7. Laissé au constructeur

- Le choix du dossier hors barème (un dossier existant, ou un nouveau seed). Contrainte : ne pas toucher aux dossiers 000001, 000003, 000004 et 000010 de la démo, ni à 000007 → 000009 (CI).
