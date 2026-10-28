# O6 — La démo des 10 minutes : parcours, livraison automatique, alerte

*Spec de la session S7 du sprint 5 — 28/10/2026. Découpage : [`2026-10-28-sprint5-sessions.md`](2026-10-28-sprint5-sessions.md). Dépend de S1, S2 et S3. Issue #157.*

## 1. Intention

Une démonstration **répétée**, qui **tient en 10 minutes** et **montre du réel** (modalités du brief). Elle doit montrer trois choses : le parcours principal, une **livraison automatique** (une fusion sur `main` qui lance `ci-cd.yml`) et une **alerte déclenchée** par une dérive simulée. Compétences : **C6** (présenter un travail en synthétisant résultats et démarche), C11, C20, C21 en appui.

## 2. Objectifs

1. `docs/demo-sprint5.md` : un scénario minuté. Chaque étape donne l'action à l'écran, la phrase à dire, le temps et le plan B. C'est le format de `Préparation de la démo du vendredi 30/10` et de `docs/demo-atelier-4.md`, réutilisé.
2. Une **liste de préparation** à faire avant la démo (T − 30 min), et les onglets à ouvrir.
3. **Deux répétitions** chronométrées, consignées (durée réelle par étape, ce qui a dérapé, la correction).

## 3. Les contraintes de temps, mesurées

| Fait | Valeur | Source |
|---|---|---|
| Durée d'un run complet de `ci-cd.yml` sur `main` | ≈ **28 min** (run du 28/10, 00:12 → 00:40) | `gh run list` |
| Délai panne → e-mail d'alerte | ≈ 5 à 10 min (évaluation toutes les 5 min, plus l'ingestion) | spec S2 |
| `make recette ACTION=llm-off` jusqu'à la révision prête | variable (`recette.sh` attend jusqu'à 5 min) | infra/recette.sh |
| Une évaluation | p95 14,9 s | evals-2026-10-27.json |

Conséquence : **ni la livraison ni l'alerte ne tiennent dans la fenêtre si on les lance pendant la démo**. Les deux sont donc lancées **avant**, et la démo montre leur avancement en direct.

## 4. Déroulé proposé (*mon choix*, à valider en répétition)

| Avant / Temps | Séquence | Ce qui est réel |
|---|---|---|
| T − 30 min | Fusionner une petite PR préparée (un changement visible et sans risque, par exemple le numéro de version affiché) → `ci-cd.yml` démarre | run GitHub en direct |
| T − 12 min | `make recette ACTION=llm-off` sur le staging | nouvelle révision du cluster |
| T − 10 min | Lancer une évaluation en staging : elle part en `REVUE_HUMAINE`, cause `llm_ko` (déclencheur de l'alerte AL-2) | `audit.evaluation`, alerte en cours d'évaluation |
| 0:00 – 1:00 | Le problème, la solution en une phrase, le schéma | — |
| 1:00 – 4:00 | Parcours principal en **production** : connexion, dossier, évaluation, frise, détail d'étape avec `trace_id`, revue humaine, contrat | espace gestionnaire |
| 4:00 – 5:30 | La **même évaluation** dans App Insights : Transaction Diagnostics, Application Map, Live Metrics | App Insights |
| 5:30 – 7:00 | Le **tableau de bord** de production, lu comme un non-développeur | Azure Dashboard |
| 7:00 – 8:30 | **L'alerte** : l'e-mail AL-2 reçu, le tableau de bord de staging, la fiche AL-2 de `docs/exploitation.md`, l'action (`make recette ACTION=llm-on`) | boîte mail, staging |
| 8:30 – 9:30 | **La livraison** : le run lancé à T − 30, ses étapes vertes, puis l'approbation de la production cliquée en direct | GitHub Actions |
| 9:30 – 10:00 | Ce qui reste, et ce que j'ai appris | — |

Plan B, pour chaque étape. Si l'e-mail n'est pas arrivé, on montre l'alerte « déclenchée » dans Azure Monitor et l'e-mail d'une répétition. Si le run échoue, on montre la porte qui a bloqué : c'est aussi du réel. Si la production n'est pas disponible, on bascule sur le staging, puis sur `make up`.

## 5. Non-objectifs

- Rejouer la démo C9/C10 du 30/10 en entier : seul le parcours principal est repris.
- Montrer S4 (D26) ou S5 (GLM) : une phrase dans « ce qui reste » au plus, sauf s'ils sont livrés.

## 6. Anti-objectifs

- Une démo qui dépasse 10 min ou qui montre une capture à la place d'un système qui tourne, alors que le système était disponible.
- Une fusion de démo qui embarque un changement risqué, ou qui ressème une base dont la démo a besoin. La fusion redéploie et ressème le staging et la production : les dossiers montrés doivent être **neufs après ce déploiement**.
- La recette `llm-off` laissée active après la démo.

## 7. Contraintes

- Démo en production pour le parcours, en staging pour la panne (décision du 28/10 : `llm-off` en staging).
- Le gestionnaire de démo : `🔴 À CONFIRMER`. Le formateur a été A pour la démo du 30/10 ; il faut confirmer qui est A pour la démo du sprint 5, et le seed de `SEED_GESTIONNAIRE_A` qui en découle.
- Date de la démo du sprint 5 (atelier n° 5) : `🔴 À CONFIRMER`.

## 8. Preuves de fin de session

- `docs/demo-sprint5.md`, et deux répétitions consignées (durées réelles ≤ 10 min).
- L'e-mail d'alerte et le run `ci-cd.yml` d'une répétition, cités avec leur date.

## 8 bis. Correction de la chronologie (relecture du 28/10, *mes choix*)

Le déroulé du §4 avait deux défauts :
- une fusion redéploie le staging, ce qui remet `INSURFLOW_LLM_ACTIF=true` et peut effacer `llm-off` ;
- les evals de staging échoueraient si `llm-off` était actif pendant leur passage.

Règles corrigées :
1. **Première répétition** : on mesure la durée de chaque étape du run (jusqu'au staging, jusqu'à la fin des evals, attente de l'approbation). Les 28 min du 28/10 incluent la production.
2. **Fusion lancée assez tôt** pour que le run soit **en attente d'approbation de la production** avant T − 15 min. *Estimation à confirmer par la mesure* : vers T − 50 min.
3. `llm-off` est lancé **seulement quand le run attend l'approbation**, donc staging déployé et evals passées. Puis une évaluation en staging. On compte sur l'e-mail AL-2 environ 5 à 10 min plus tard.
4. **L'approbation de la production est cliquée en direct** (8:30). Le déploiement de production, qui ressème la base, a donc lieu **après** le parcours. Les dossiers du parcours viennent du déploiement de la veille au soir.
5. Après la démo : `make recette ACTION=llm-on`.

**Répétitions** : chaque répétition fusionne une vraie petite PR utile (par exemple une PR de doc de S6) et va jusqu'à l'approbation. Approuver la production y est facultatif ; refuser l'approbation arrête le run sans rien casser. Les versions publiées par l'étape `release` sont acceptées : elles ne coûtent rien.

**Dépendances** : S1, S2 **et** S3 sont fusionnées avant la première répétition. S'il en manque une, la séquence correspondante passe en plan B (capture d'une répétition) et le constat est noté.

## 9. Laissé au constructeur

- Le choix exact de la PR de démo.
- Les phrases à dire, dans l'esprit du document du 30/10 : courtes, et chacune rattachée à une preuve.
