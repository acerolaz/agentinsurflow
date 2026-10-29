# Recette C11 (monitorer le modèle) — AAAA-MM-JJ (gabarit à remplir)

C11 : métriques suivies (qualité, latence, coût), outils de collecte, d'alerte et de restitution. Écart à lever : aucune évaluation réelle visible dans Application Insights (#176). Pas à pas : [`observabilite-app-insights.md`](../../docs/observabilite-app-insights.md) §§ 2, 5, 7 ; panne type : [`exploitation.md`](../../docs/exploitation.md) « La panne type : le LLM coupé (alerte AL-2) ».

- **Environnements** : production (collecte) et staging (alerte), release **vX.Y.Z**, SHA `…` (`/health`).
- **Acteurs** : Acerola pilote ; vérifications en lecture seule. Heures en UTC.
- **Préalable** : `make vigie ENV=staging` et `make vigie ENV=production` déjà appliqués (tableaux de bord et AL-1 → AL-10 présents).
- **Captures** : à verser à côté de ce fichier, nommées `recette-c11-AAAA-MM-JJ-<n>.png`.

## 1. Collecte — une évaluation tracée de bout en bout (production)

Dossier : `AIF-2026-0000NN` (jamais `000007` à `000009`, réservés à la CI).

| Heure | Étape | `trace_id` |
|---|---|---|
| … | Lancer l'évaluation depuis `https://aibrokerflow.fr/app/` | … |

Dans `appi-insurflow-production` › Recherche de transactions, avec ce `trace_id` :

- ⬜ Arbre complet : gateway → cluster → 4 spans `invoke_agent` → MCP, Function de calcul, LLM (capture 1).
- ⬜ Propriétés d'un agent : mode, durée, tokens ; aucune donnée personnelle, seulement des empreintes.
- ⬜ Services présents sur 7 jours (requête du § 8 de `observabilite-app-insights.md`) : … services, dont `agentic-cluster`.

## 2. Alerte — AL-2 déclenchée puis retombée (staging)

| Heure | Événement | Preuve |
|---|---|---|
| … | `make recette ACTION=llm-off` : « prête, 100 % du trafic » | — |
| … | Évaluation `AIF-2026-0000NN` : revue humaine, « Service temporairement indisponible » | `trace_id` … |
| … | **E-mail AL-2** reçu (groupe `ag-insurflow-staging`) | capture 2 |
| … | `al-2-llm-ko.kql` : `valeur` = … | capture 3 |
| … | `make recette ACTION=llm-on` : « prête, 100 % du trafic » | — |
| … | Nouvelle évaluation passée LLM actif ; `valeur` = 0 après 5 min | capture 4 |

Résultat : ⬜ (alerte reçue en ≤ 10 min, puis retour à la normale).

## 3. Restitution — tableaux de bord

| Tuile | `vigie-production` | `vigie-staging` |
|---|---|---|
| Disponibilité | … | … |
| Évaluations par heure | … | … |
| p95 (latence) | … s | … s |
| Revue humaine par cause | … | `llm_ko` : … |
| Coût par agent | … | … |
| Évaluations sans décision | … | … |

- ⬜ Les évaluations des §§ 1 et 2 apparaissent dans les tuiles (captures 5 et 6).
- ⬜ Surveillance › Alertes : AL-2 vue déclenchée en staging (capture 7).

## Bilan

- C11 : ⬜ ✅ / 🟡 — à reporter dans [`soutenance-2026-10-30.md`](../../docs/dossier/soutenance-2026-10-30.md) (ligne C11) ; #176 fermée si le § 1 est vert.
- Défauts trouvés : …
