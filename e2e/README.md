# Tests E2E

La solution qui tourne (compose ou staging), toujours jointe par la gateway.

```bash
make up
make test-e2e URL=http://localhost:8000      # staging : URL=https://<domaine>
```

- Jetons : `E2E_JETON_GESTIONNAIRE` (audience rag), `E2E_JETON_GESTIONNAIRE_UNDERWRITING`, `E2E_JETON_INGESTION`, `E2E_JETON_MCP` (audience `agentinsurflow-mcp`) ; à défaut `az account get-access-token --resource api://agentinsurflow-…` (lecture seule). Sans jeton, le test est sauté avec la raison.
- `test_mcp_liste_filtree_et_refus_type` : un jeton d'utilisateur n'est l'`azp` d'aucun agent, donc liste d'outils vide et `search_rag` refusé (`UNAUTHORIZED_TOOL`). `/health/mcp` et le 401 sans jeton n'ont pas besoin de jeton.
- Sautés en local : `test_seule_la_gateway_est_exposee` et `test_ip_client_reelle_dans_les_spans` (staging seulement).
- `test_contrat_d_un_autre_gestionnaire_404_via_reponses` est sauté avec un jeton d'application (CI) : Entra ne fait l'On-Behalf-Of qu'avec un jeton d'utilisateur. Ce chemin se vérifie avec un compte humain (démo), après le consentement administrateur de la permission `agentinsurflow-rag` → `access_as_user`.
- Sautés si l'environnement est incomplet (503 `EMBEDDINGS_INDISPONIBLES` : `GATEWAY_CLIENT_SECRET` ou `RAG_CLIENT_SECRET` absent du compose, donc pas de jeton pour le canal LLM de la gateway ; 503 `DOSSIERS_INDISPONIBLES` : `RAG_CLIENT_SECRET` absent, donc pas d'OBO).
- `test_ingestion_rejouée…` rejoue le dernier instantané de `data/raw/` deux fois (`make ingest`) : aucun appel Légifrance.
- Le seed attribue `AIF-2026-000001` à `000003` au gestionnaire A et `000004` à `000006` au gestionnaire B. Le test BOLA vise `AIF-2026-000004` : l'identité qui lance les E2E doit être le gestionnaire A (`SEED_GESTIONNAIRE_A`), jamais B.

## Manque d'environnement : skip en local, échec ailleurs

- Un manque d'environnement (jeton introuvable, instantané absent, 503 `EMBEDDINGS_INDISPONIBLES` ou `DOSSIERS_INDISPONIBLES`) est **sauté en local seulement**. Il devient un **échec** si `E2E_URL` n'est pas local ou si `E2E_STRICT=1` : un staging cassé ne peut pas rester vert.
- Seuls ces deux codes 503 comptent comme manque ; tout autre 503, ou un corps non JSON, est un échec.
- `E2E_CONTRAT_PROPRE` : un contrat du gestionnaire connecté (témoin positif du test BOLA : `GET /api/contrats/{propre}` = 200, listé par `GET /api/contrats`, sans `AIF-2026-000004`). Exigée hors local ou en mode strict ; facultative en local (seul ce témoin est alors omis).
