# O2 + O3 — Tableau de bord Azure et alertes à seuils argumentés

*Spec de la session S2 du sprint 5 — 28/10/2026. Découpage : [`2026-10-28-sprint5-sessions.md`](2026-10-28-sprint5-sessions.md). Dépend de S1 ([`2026-10-28-o1-instrumentation-app-insights-design.md`](2026-10-28-o1-instrumentation-app-insights-design.md)) déployée en staging.*

## 1. Intention

Rendre le système **pilotable par quelqu'un qui n'a pas écrit le code** :
- un **tableau de bord** qu'un non-développeur comprend **sans explication orale** (modalité d'évaluation du brief) ;
- pour chaque signal clé, **un seuil argumenté, une alerte par e-mail, une action documentée** ; une **dérive simulée en direct** doit déclencher l'alerte prévue (modalité « live »).

Compétences servies : C11 (restitution temps réel, accessibilité de l'outil, chaîne en état de marche), C20 (métriques + seuils + valeurs d'alerte documentés, alertes en état de marche).

## 2. Objectifs

1. `infra/vigie.sh` complet (étendu depuis l'étape App Insights de S1), `make vigie ENV=staging|production`, idempotent, lancé **à la main** par Acerola :
   1. Action Group e-mail (`az monitor action-group create`) ;
   2. règles d'alerte (`az monitor scheduled-query create`, plus un test de disponibilité si retenu, §5) ;
   3. tableau de bord (`az portal dashboard create` depuis `infra/vigie/dashboard.json`).
2. `infra/vigie/dashboard.json` **versionné**, paramétré par environnement (identifiants de ressources substitués au lancement, comme les `infra/containerapp*.yaml` le sont par `envsubst`).
3. Les requêtes KQL des alertes et des tuiles **versionnées dans des fichiers** (`infra/vigie/kql/*.kql`), une source unique pour le tableau de bord, les alertes et la doc (S3).
4. Le **catalogue des signaux** (§4) recopié dans `docs/contrat-personnel.md` §4 avec la requête **validée**, le seuil, la mesure source, l'alerte et l'action.
5. Preuve de la **dérive simulée** en staging (§7).

## 3. Non-objectifs

- `docs/exploitation.md` : **S3** (S2 ne fait que nommer, pour chaque alerte, l'ancre de section que S3 rédigera).
- **A8** (évaluation en ligne < 0,8) : aucune évaluation en ligne n'existe en production ; les evals tournent dans la CI (porte 3). Cité comme limite connue, pas d'alerte.
- Faux positifs des garde-fous en ligne : hors ligne seulement (`make garde-fous`).
- Grafana, Workbooks, Power BI : **écartés** (outil décidé : Azure Dashboard).

## 4. Catalogue des signaux et seuils

Règle (D-V6, Acerola) : chaque seuil est **dérivé d'une mesure ou d'un budget existant**, sinon `🔴` jusqu'à une ligne de base de 7 jours en staging. Les lignes 💡 sont les propositions d'Acerola du 28/10, reprises telles quelles comme base de travail.

| # | Signal | Seuil | Argument (mesure source) | Action liée (ancre de `docs/exploitation.md`, S3) | Statut |
|---|---|---|---|---|---|
| AL-1 | Latence p95 d'une évaluation (`audit.evaluation.duree_ms`) | **> 30 s** sur 15 min | SLO-2 (p95 ≤ 30 s) ; garde globale 25 s + 2 s ; p95 mesurée 14,9 s le 27/10 (`eval/preuves/evals-2026-10-27.json`) | Trace la plus lente (Transaction Diagnostics) → agent en cause → `agents.toml` | 💡 |
| AL-2 | Erreurs `llm_ko` (`audit.agent.cause`) | **≥ 1** en 5 min | 0 en nominal depuis `gpt-4.1-mini` (#105) ; `llm_ko` = panne du LLM (K5) | `INSURFLOW_LLM_ACTIF`, `/health/cluster`, quota Foundry ; sinon `make rollback` | 💡 |
| AL-3 | Cluster en `503 GARDE_FOUS_EN_CHARGEMENT` | **> 3 min** | Sonde de démarrage ≈ 3 min autorisées ; chargement ≈ 6 s en local (`docs/contrat-personnel.md` §4) | Journaux de la réplique ; redémarrage (`make recette ACTION=redemarrer` en staging) | 💡 |
| AL-4 | `MCP_INDISPONIBLE` (502 `OUTIL_INDISPONIBLE`) | **≥ 1** en 5 min | 0 en nominal ; délai MCP 22 s (#146) | `/health/mcp` → journaux du serveur MCP → rollback | 💡 |
| AL-5 = **A7** | Part des évaluations terminées en `REVUE_HUMAINE` | **> 30 %** sur 2 h glissantes, si **≥ 10** évaluations | SLO-5 (≤ 20 %), alerte A7 du dossier (L7.5) ; volume minimal 💡 | Cause dominante (garde-fou, `llm_ko`, `duree`) → section correspondante | 💡 |
| AL-6 = **A6** | Coût IA moyen par dossier évalué | **> 0,15 €** sur 24 h glissantes, vérifié toutes les heures | SLO-6 ; coût = Σ jetons × prix (Global, D-V15) × taux USD → € | Agent et modèle les plus coûteux → `max_tokens` dans `agents.toml` | 💡 ; taux `🔴` |
| AL-7 = **A10** | Taux d'évaluations refusées par un garde-fou (`cause` `garde_fou:*`) | **> 2×** sa moyenne sur 7 jours, sur 1 h, si **≥ 10** évaluations | Alerte A10 du dossier ; moyenne **calculée dans la requête** | Échantillon des causes → attaque ou faux positifs → `make garde-fous` | 💡 |
| AL-8 = **A5** | 429 de Foundry vus par la gateway (dépendance `/api/llm`) | `🔴 À CONFIRMER` | Alerte A5 du dossier (L7.5) : reprendre sa formulation exacte ; sinon ligne de base 7 j | Quota / capacité du déploiement (5 750 k TPM pour gpt-4.1-mini) | `🔴` |
| AL-9 = **A11** | 403 de la gateway après un déploiement | `🔴 À CONFIRMER` | Alerte A11 du dossier (L7.5) ; ligne de base 7 j des 403 hors déploiement | Rôles Entra / `make entra` ; rollback si régression | `🔴` |
| — | **SLO-4** évaluations sans décision (`audit.evaluation.statut_final` en erreur) | **< 1 %** affiché ; alerte `🔴` | SLO-4 du dossier (L7.5) | — | tuile seule |

Pour AL-8, AL-9 et SLO-4 : le constructeur **lit `dossier-conception-v1.2.pdf` L7.5** ; si le dossier donne une valeur, il la cite ; sinon la règle est créée **désactivée** et le seuil reste `🔴` (jamais inventé).

**Paramètres** (en tête de `infra/vigie.sh`, surchargeables par `.env`) : prix unitaires par modèle (D-V15, valeurs Global), `TAUX_USD_EUR` (**`🔴`, sans valeur par défaut** : si absent, la règle AL-6 n'est pas créée et le script le dit), destinataire `ALERTE_EMAIL`.

## 5. Décisions prises

| Décision | Par |
|---|---|
| Tableau de bord : **Azure Dashboard**, lisible par un non-développeur | Acerola |
| Alertes : **Azure Monitor → Action Group → e-mail** à `svespuce.ext@simplonformations.co` (D-V5b) | Acerola |
| Format versionnable : script `az` + `sh` + cible `make`, lancé à la main (D-V4) | Acerola |
| Dérive à montrer en direct : `make recette ACTION=llm-off` **en staging** → AL-2 | Acerola (28/10) |
| **Les alertes existent dans les deux environnements**, mêmes seuils. AL-2 n'exclut donc pas la recette en staging : c'est justement elle qui sert à la démo. En production, une recette n'est jamais jouée (`recette.sh` vise staging par défaut). | *mon choix* |
| Règles de requête planifiée évaluées **toutes les 5 min** (AL-2, AL-3, AL-4), 15 min (AL-1), 1 h (AL-5 → AL-9) ; résolution automatique activée | *mon choix* (délai panne → e-mail ≈ 5 à 10 min, compatible avec une démo de 10 min si la panne est lancée au début) |
| Un tableau de bord **par environnement** (staging, production) | *mon choix* |
| Un **test de disponibilité standard** d'App Insights sur `GET /health` de la gateway (tuile « Le service répond-il ? ») | *mon choix* |

## 6. Le tableau de bord — ce que voit un non-développeur

Principe : **chaque tuile répond à une question écrite en français courant**, affiche l'**objectif en texte** à côté de la valeur, et ne porte **jamais l'information par la seule couleur** (accessibilité, C11/C20). Période par défaut : 24 h ; actualisation automatique.

| Tuile (titre = question) | Contenu | Objectif écrit sur la tuile |
|---|---|---|
| Comment lire ce tableau | Texte (Markdown) : à quoi sert la page, que faire si une tuile est « hors objectif » (lien vers `docs/exploitation.md`) | — |
| Le service répond-il ? | Test de disponibilité de `/health` (%) | 100 % |
| Combien de dossiers évalués ? | Nombre d'`audit.evaluation`, par heure | — |
| Combien de temps prend une évaluation ? | p95 de `duree_ms` + courbe | ≤ 30 s (SLO-2) |
| Quelle part part en revue humaine, et pourquoi ? | % `REVUE_HUMAINE` + répartition par cause | ≤ 20 % (SLO-5) ; alerte > 30 % |
| Combien coûte un dossier ? | € moyen par dossier, par agent et modèle | ≤ 0,15 € (SLO-6) |
| Les garde-fous bloquent-ils plus que d'habitude ? | Taux de refus 1 h vs moyenne 7 j | alerte > 2× |
| Combien d'évaluations sans décision ? | % erreurs | < 1 % (SLO-4) |
| Le modèle de langage est-il disponible ? | Nombre de `llm_ko` et de 429 | 0 |
| Alertes en cours | Alertes Azure Monitor déclenchées | aucune |

Le **vecteur temps réel** exigé par C11 : Live Metrics (S1) + l'actualisation automatique du tableau de bord.

## 7. Preuves de fin de session

1. `make vigie ENV=staging` puis `ENV=production` passent ; un second lancement ne change rien (idempotence).
2. **Dérive simulée** en staging : `make recette ACTION=llm-off`, une évaluation, **e-mail AL-2 reçu** ; heure de la panne, heure de l'e-mail et capture consignées dans `eval/preuves/alerte-<date>-staging.md` ; puis `make recette ACTION=llm-on` et e-mail de résolution.
3. **Test de lecture** : une personne non développeuse répond seule, devant le tableau de bord, à 5 questions écrites à l'avance (« Le service va-t-il bien ? », « Combien de dossiers aujourd'hui ? », « Le délai est-il dans l'objectif ? », « Coûte-t-on trop cher ? », « Y a-t-il une alerte ? ») ; ses réponses et chaque hésitation sont consignées (base de la grille de retours).
4. Chaque requête de `infra/vigie/kql/` exécutée en staging avec un résultat non vide (ou vide, expliqué).
5. Le catalogue du §4 recopié dans `docs/contrat-personnel.md` §4, requêtes validées.

## 8. Contraintes

- Gel des fusions sur `main` du 29/10 au matin à la fin de la démo du 30/10.
- Écritures Azure seulement par `make vigie`, lancé à la main par Acerola.
- Les requêtes filtrent par ressource App Insights (`_ResourceId`) : un seul workspace pour staging et production (D-V1).
- Aucun seuil inventé (§4).

## 9. Laissé au constructeur

- Le schéma JSON des tuiles du tableau de bord (tuiles de requête Log Analytics, Markdown, disponibilité) et la mise en page.
- La forme exacte de la règle AL-3 (journaux système de la Container App, `ProbeFailed`, ou test de disponibilité sur `/health/cluster`), tant que le seuil reste « > 3 min ».
- Les gravités des alertes et le texte de l'e-mail (il doit contenir le nom de l'alerte, l'environnement et le lien vers la section de `docs/exploitation.md`).
