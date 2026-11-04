# Benchmark des modèles Foundry (C7) : procédure

Candidats, tous en Global Standard sur la ressource `swedencentral` : `gpt-4.1-mini`, `gpt-5-mini`, `Kimi-K2.5`.
Critères fixés avant la mesure : `docs/superpowers/specs/2026-11-03-e2-rapport-design.md` §6.2.

**Limites à annoncer** : jeu d'évaluation réduit, mesures depuis un poste local (latences comparables entre modèles, pas à la production), appels isolés par agent (coût par dossier approximé, sur les seules mesures réussies, sans Saga complète), réglages de `agents.toml` non adaptés par modèle (ils ont été réglés sur `gpt-4.1-mini` : le verdict de `gpt-5-mini` vaut pour ces réglages), `llm_ko` non attribuable (modèle, limite de débit de la gateway ou Foundry : un 429 n'est distingué que par l'appel de contrôle).

## Lancer la campagne (Acerola, depuis ce worktree)

```bash
# 1. Préparer : la solution du dépôt principal doit être arrêtée (mêmes ports).
cp ../../../.env .env
bash infra/benchmark-e2.sh creer   # écriture Entra : secret temporaire du rag local (.env local seul)
# le jeton az a pour audience l'ID client (v2) ; sans cette ligne, la gateway locale répond 401
echo "RAG_API_AUDIENCES=$(grep -E '^RAG_API_CLIENT_ID=' .env | cut -d= -f2)" >> .env
export EVALS_JETON=$(az account get-access-token --scope "api://agentinsurflow-rag/.default" --query accessToken -o tsv)
make up
make ingest URL=http://localhost:8000 JEU=data/aggregated/corpus-2026-10-27.json

# 2. Usage RAG, trois fois (un code de sortie non nul est un résultat : garder le fichier).
for m in gpt-4.1-mini gpt-5-mini Kimi-K2.5; do
  BENCH_MODELE=$m docker compose -f docker-compose.yml -f eval/benchmark/compose-benchmark.yml up -d --wait rag
  # rag n'a pas de healthcheck : sans cette attente, les premiers cas tombent en 502 (connexion refusée)
  until docker compose exec -T rag python -c "import urllib.request as u;u.urlopen('http://localhost:8001/health',timeout=2)" 2>/dev/null; do sleep 2; done
  uv run python tools/evals.py --url http://localhost:8000 --questions eval/questions-demo.jsonl \
    --sans-dossiers --rapport eval/preuves/benchmark-2026-11-03/rag-$m.json
done

# 3. Usage agents : 108 mesures, 15 min environ.
uv run --env-file .env --project agentic-cluster python agentic-cluster/benchmark_agents.py \
  --modeles gpt-4.1-mini gpt-5-mini Kimi-K2.5 --sortie eval/preuves/benchmark-2026-11-03/agents.json

# 4. Arrêter et retirer le secret.
make down
bash infra/benchmark-e2.sh retirer
rm .env
```

Ensuite, cette commande écrit `benchmark.md` : `uv run python -m tools.benchmark_synthese --dossier eval/preuves/benchmark-2026-11-03`.

`rag/llm.env` et `agents.toml` ne sont pas modifiés. Un rapport dont `manifeste.modele.observe` diffère du modèle attendu est refusé par la synthèse.

`prix.json` : API Azure Retail Prices, relevé le 03/11/2026 (`uv run python -m tools.benchmark_synthese --prix …`).
