# Sprint 5 « La vigie & la démo » — découpage en sessions

*28/10/2026 — décidé avec Acerola (découpage A → B → C → D validé ; « une session par projet O1 à O8 »).*

Chaque session part de **sa** spec (ci-dessous), la fait approuver si elle est encore à l'état de brouillon, puis enchaîne `superpowers:writing-plans` → implémentation → PR. Une session = une branche = une PR.

| Session | Objectifs | Spec | Dépend de | Échéance |
|---|---|---|---|---|
| S1 | **O1** Instrumenter vers Application Insights (#54) | [`2026-10-28-o1-instrumentation-app-insights-design.md`](2026-10-28-o1-instrumentation-app-insights-design.md) | — | 15/11 (#54) |
| S2 | **O2 + O3** Azure Dashboard, alertes, Action Group (`infra/vigie.sh` complet) | [`2026-10-28-o2-o3-dashboard-alertes-design.md`](2026-10-28-o2-o3-dashboard-alertes-design.md) | S1 en staging | 15/11 |
| S3 | **O4** `docs/exploitation.md` (déployer · diagnostiquer · rollback, depuis le poste d'Acerola) | à écrire | S2 (actions liées aux alertes) | 15/11 |
| S4 | **O8** Suppression de D26 : checkpointer HTTP par la gateway | à écrire | — (indépendant ; traces dans App Insights si S1 fusionnée) | 15/11 |
| S5 | **O7** GLM Poisson freMTPL2 | à écrire | — | 15/11 |
| S6 | **O5** Durcissement (écarts du contrat, D-V9 → D-V12) | à écrire | — | 15/11 |
| S7 | **O6** Démo des 10 min (parcours · merge → livraison · alerte) | à écrire | S1 → S3 | répétition avant le 15/11 |

O2 et O3 sont regroupés : même script `infra/vigie.sh`, mêmes requêtes KQL.

## Contraintes communes à toutes les sessions

- **Gel du 29/10 au matin → fin de la démo du 30/10** : aucune fusion sur `main` (une fusion redéploie staging et production et ressème la base annexe, ce qui casserait la préparation de la démo C9/C10).
- Écritures Azure, Entra et `gh variable set` : **lancées à la main par Acerola**, jamais par un agent ni par la CI ; les agents écrivent les scripts.
- Aucune montée de version sans accord ; nouvelles dépendances accordées le 28/10 : `azure-monitor-opentelemetry` (Python) et `Azure.Monitor.OpenTelemetry.AspNetCore` (C#), dernière version stable figée.
- Architecture : hexagonale côté Python, Clean Architecture côté C# ; `CLAUDE.md` du dépôt (pyramide 70/20/10).
- RGPD : aucune donnée identifiante dans la télémétrie (`enable_content_recording=False`, empreintes SHA-256).
- Vocabulaire : « Saga », jamais « Harnais ».
- Seuils d'alerte : jamais inventés ; chaque seuil cite sa mesure source, sinon `🔴`.

## Faits établis le 28/10 (lecture du dépôt et d'Azure, lecture seule)

- Foundry `svespuce-971` (svespuceRG) : `gpt-4.1-mini`, `Kimi-K2.5`, `text-embedding-3-small`, tous en **GlobalStandard** → tarif **Global** (D-V15).
- La gateway ne publie **pas** d'histogramme `gen_ai.client.token.usage` : elle pose `gen_ai.usage.input_tokens` / `output_tokens` en **attributs de span** (`Program.cs`). Décision : on les garde ainsi, lus en KQL.
- `make up` lance déjà les 7 services (dont cluster, MCP, calcul) : seul le commentaire de la cible est périmé.
- L'espace gestionnaire (`wwwroot/app/dossier.js`) et l'E2E de la CI (`e2e/test_parcours.py`) lisent `GET /api/traces/{trace_id}` **en staging** : le référentiel SQL n'est pas « local seulement » (voir D-V2 amendée dans la spec S1).
