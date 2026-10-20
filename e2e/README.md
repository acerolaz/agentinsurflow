# Tests E2E

La solution qui tourne (compose ou staging), toujours jointe par la gateway.

```bash
make up
make test-e2e URL=http://localhost:8000      # staging : URL=https://<domaine>
```

- Jetons : `E2E_JETON_GESTIONNAIRE` (audience rag), `E2E_JETON_GESTIONNAIRE_UNDERWRITING`, `E2E_JETON_INGESTION` ; à défaut `az account get-access-token --resource api://agentinsurflow-…` (lecture seule). Sans jeton, le test est sauté avec la raison.
- Sautés en local : `test_seule_la_gateway_est_exposee` et `test_ip_client_reelle_dans_les_spans` (staging seulement).
- Sautés si l'environnement est incomplet (503 `EMBEDDINGS_INDISPONIBLES` : clé Azure OpenAI absente du compose ; 503 `DOSSIERS_INDISPONIBLES` : `RAG_CLIENT_SECRET` absent, donc pas d'OBO).
- `test_ingestion_rejouée…` rejoue le dernier instantané de `data/raw/` deux fois (`make ingest`) : aucun appel Légifrance.
- Le contrat `AIF-2026-0001` doit appartenir à un autre gestionnaire que l'utilisateur connecté (seeds `SEED_GESTIONNAIRE_A/B`).
