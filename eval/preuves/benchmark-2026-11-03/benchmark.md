# Benchmark des modèles Foundry

## Usage RAG

| Modèle | Taux | Latence p95 (s) | Cas |
|---|---|---|---|
| `Kimi-K2.5` | 1.00 | 24.12 | 11 |
| `gpt-4.1-mini` | 1.00 | 4.15 | 11 |
| `gpt-5-mini` | 0.82 | 11.36 | 11 |

## Usage agents

| Modèle | Agent | Réussites | p50 (s) | p95 (s) | Tokens entrée | Tokens sortie | Échecs |
|---|---|---|---|---|---|---|---|
| `Kimi-K2.5` | pieces | 9/9 | 2.60 | 4.49 | 305 | 194 | aucun |
| `Kimi-K2.5` | analyste | 9/9 | 2.90 | 3.94 | 329 | 287 | aucun |
| `Kimi-K2.5` | redacteur | 8/9 | 8.10 | 15.85 | 4175 | 668 | budget_tokens : 1 |
| `Kimi-K2.5` | actuaire | 9/9 | 2.54 | 3.63 | 313 | 204 | aucun |
| `gpt-4.1-mini` | pieces | 9/9 | 1.39 | 1.70 | 263 | 25 | aucun |
| `gpt-4.1-mini` | analyste | 9/9 | 1.30 | 1.51 | 285 | 89 | aucun |
| `gpt-4.1-mini` | redacteur | 8/9 | 4.55 | 6.23 | 3684 | 116 | llm_ko : 1 |
| `gpt-4.1-mini` | actuaire | 9/9 | 1.86 | 2.90 | 274 | 63 | aucun |
| `gpt-5-mini` | pieces | 1/9 | 3.34 | 3.34 | 352 | 354 | budget_tokens : 8 |
| `gpt-5-mini` | analyste | 0/9 | — | — | — | — | budget_tokens : 9 |
| `gpt-5-mini` | redacteur | 7/9 | 16.82 | 21.98 | 5397 | 1455 | budget_tokens : 2 |
| `gpt-5-mini` | actuaire | 0/9 | — | — | — | — | budget_tokens : 9 |

## Coût par dossier et verdict

Coût approximé : somme des coûts moyens de quatre agents, sur les seules mesures réussies, hors Saga complète.

Verdict : taux ≥ 0,8 et au moins une réussite par agent. Le critère « déployable » n'est pas mesuré ici : il vient de la lecture des déploiements de la ressource.

| Modèle | Coût par dossier (USD) | Verdict sur les critères bloquants |
|---|---|---|
| `Kimi-K2.5` | 0.0078 (réf. Data Zone) | répond |
| `gpt-4.1-mini` | 0.0023 | répond |
| `gpt-5-mini` | — | ne répond pas |
