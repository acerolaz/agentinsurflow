# Recette K11 en staging — AAAA-MM-JJ (gabarit à remplir à la Task 7)

Rejeu de K11 après D106 (points de reprise par la gateway vers underwriting-admin). Référence : [`recette-k-2026-10-27-staging.md`](recette-k-2026-10-27-staging.md), § K11.

- **Environnement** : staging (`insurflow-staging`), release **vX.Y.Z**, SHA `…` (`/health`).
- **Acteurs** : Acerola pilote ; vérifications en lecture seule. Heures en UTC.
- **Préalables (à la main, Acerola)** : `make entra`, `make annexe` avant le premier run de `deploy.yml`.

## Commande et résultat

Commande : `make recette ACTION=redemarrer` (dossier : `AIF-2026-0000NN`).

| Heure | Événement | Trace |
|---|---|---|
| … | Pièces (llm) | … |
| … | Analyste (llm), puis **Pause** | … |
| … | **Nouvelle réplique** du cluster | — |
| … | Rédacteur, **même tentative**, puis `EN_ANALYSE` | … |

Résultat : ⬜ (reprise à l'étape suivante, sans rejouer Pièces ni l'Analyste).

## Allers-retours par évaluation

Référence mesurée à la Task 5, **sur le faux underwriting-admin** (`test_reprise_apres_interrupt_par_http`), avec un état de test **réduit** (pas un point réel PostgreSQL) :

| Scénario | GET | PUT de point | PUT d'écritures | PUT maximal |
|---|---|---|---|---|
| Évaluation | 4 | 8 | 8 | 3 564 o |
| Reprise | 3 | 2 | 3 | 3 996 o |

Relevé staging (App Insights, dépendances, ou référentiel des traces) :

| Scénario | GET | PUT de point | PUT d'écritures | PUT maximal |
|---|---|---|---|---|
| Évaluation | … | … | … | … |
| Reprise | … | … | … | … |

## Latence

- p95 des evals (porte : ≤ 30 s) : … s, avant D106 : … s.
- **p95 ajouté** par les points de reprise : … s (garde globale du cluster : 25 s).
