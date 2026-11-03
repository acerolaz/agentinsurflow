# Benchmark des modèles Foundry (C7) : procédure

Candidats, tous en Global Standard sur la ressource `swedencentral` : `gpt-4.1-mini`, `gpt-5-mini`, `Kimi-K2.5`.
Critères fixés avant la mesure : `docs/superpowers/specs/2026-11-03-e2-rapport-design.md` §6.2.

**Limites à annoncer** : jeu d'évaluation réduit, mesures depuis un poste local (latences comparables entre modèles, pas à la production), appels isolés par agent (coût par dossier approximé, sans Saga complète).

## Lancer la campagne (Acerola, depuis ce worktree)

```bash
# 1. Préparer : la solution du dépôt principal doit être arrêtée (mêmes ports).
cp ../../../.env .env
export EVALS_JETON=$(az account get-access-token --scope "api://agentinsurflow-rag/.default" --query accessToken -o tsv)
make up
make ingest URL=http://localhost:8000 JEU=data/aggregated/corpus-2026-10-27.json

# 2. Usage RAG, trois fois (un code de sortie non nul est un résultat : garder le fichier).
for m in gpt-4.1-mini gpt-5-mini Kimi-K2.5; do
  BENCH_MODELE=$m docker compose -f docker-compose.yml -f eval/benchmark/compose-benchmark.yml up -d --wait rag
  uv run python tools/evals.py --url http://localhost:8000 --questions eval/questions-demo.jsonl \
    --sans-dossiers --rapport eval/preuves/benchmark-2026-11-03/rag-$m.json
done

# 3. Usage agents : 108 mesures, 15 min environ.
uv run --env-file .env --project agentic-cluster python agentic-cluster/benchmark_agents.py \
  --modeles gpt-4.1-mini gpt-5-mini Kimi-K2.5 --sortie eval/preuves/benchmark-2026-11-03/agents.json

# 4. Arrêter.
make down
```

Ensuite, Claude écrit `benchmark.md` : `uv run python -m tools.benchmark_synthese --dossier eval/preuves/benchmark-2026-11-03`.

`rag/llm.env` et `agents.toml` ne sont pas modifiés. Un rapport dont `manifeste.modele.observe` diffère du modèle attendu est refusé par la synthèse.

`prix.json` : API Azure Retail Prices, relevé le 03/11/2026 (`uv run python -m tools.benchmark_synthese --prix …`).
