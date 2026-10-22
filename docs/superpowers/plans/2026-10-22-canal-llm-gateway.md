# Canal LLM par la gateway — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Tout appel au LLM (Foundry) passe par la gateway, qui échange le jeton, limite le débit par appelant et mesure les tokens ; Foundry n'accepte que la gateway ; rag sort dans sa propre Container App.

**Spec:** [`docs/superpowers/specs/2026-10-22-canal-llm-gateway-design.md`](../specs/2026-10-22-canal-llm-gateway-design.md) (approuvée par Acerola le 22/10, « tout par la gateway, y compris en local »).

## Global Constraints

- Branche `feat/llm-gateway` (partie de `feat/RiskPrime`), commits locaux ; jamais de push sur `main`.
- Aucune nouvelle dépendance ni changement de version (`Azure.Identity` déjà dans la gateway ; `openai`, `azure-identity` déjà dans rag).
- `gateway/CLAUDE.md` : refus par défaut, rôle **et** audience par route, ProblemDetails avec `code`.
- Jamais de prompt, réponse, jeton ou `numero_contrat` dans une trace, une métrique ou un journal.
- Aucun secret dans le dépôt ; scripts `infra/*.sh` rédigés, jamais lancés par un agent ; aucune commande `az`.
- Exploration : graphify d'abord (`graphify query "<q>" --graph /Volumes/CodeSource/myRepos/simplon/certification/graphify-out/graph.json`).

---

### Task 1: Route `llm` et échange de jeton généralisé (gateway)

**Files:** `gateway/src/AgentInsurFlow.Gateway.Api/Program.cs`, `appsettings.Routes.json`, `appsettings.json`, tests `gateway/tests/…/LlmTests.cs` (+ `CalculTests.cs` inchangés et verts), `docker-compose.yml` (gateway), `gateway/README.md`.

**Interfaces :**
- `POST /api/llm/{**reste}` → cluster `llm` (destination `ReverseProxy__Clusters__llm__Destinations__d1__Address` = endpoint Foundry), chemin réécrit `/openai/{**reste}`.
- Politique `llm-appelant` : rôle `LLM` + `Entra:Audiences:llm` (api:// et GUID). Limite de débit `llm` partitionnée par **`azp`** (repli `appid` pour un jeton v1), `RateLimit:Llm:PermitLimit`.
- Sans tampon de réponse (vérifier qu'aucune option de YARP ne tamponne ; test de streaming : le client reçoit le premier fragment avant la fin).
- Échange de jeton généralisé : une table route → portée (`Calcul:Portee`, `Llm:Portee` = `https://cognitiveservices.azure.com/.default`) au lieu du `if RouteId == "calcul"` ; échec → 502 avec code par route (`CALCUL_INDISPONIBLE`, `LLM_INDISPONIBLE`).
- Credential : `ClientSecretCredential(tenant, Gateway:ClientId, Gateway:ClientSecret)` si le secret est configuré (local), sinon `ManagedIdentityCredential` comme aujourd'hui.

- [ ] Tests d'abord (WireMock) : routage `/api/llm/v1/chat/completions` → `/openai/v1/chat/completions` avec le jeton **de la gateway** ; 401 ; 403 sans rôle `LLM` ; 403 mauvaise audience ; GUID accepté ; 429 par `azp` (deux `azp` différents ont chacun leur quota) ; échec du credential → 502 `LLM_INDISPONIBLE` sans détail ; streaming non tamponné ; calcul inchangé ; choix du credential (secret → `ClientSecretCredential`). Échec montré.
- [ ] Implémenter ; `dotnet test gateway` ; `dotnet format --verify-no-changes`.
- [ ] Commit `feat(gateway): route llm vers Foundry, échange de jeton généralisé, débit par azp (#70)`.

### Task 2: Mesure des tokens (gateway)

**Files:** `gateway/src/AgentInsurFlow.Gateway.Api/Program.cs` (ou un fichier dédié si Program.cs grossit), tests `LlmTests.cs`, `gateway/README.md`.

- Sur la route `llm`, réponse `application/json` seulement : lire `usage.prompt_tokens`, `usage.completion_tokens` et émettre l'histogramme OTel `gen_ai.client.token.usage` (attributs `appelant.azp`, `gen_ai.token.type` = `input`/`output`, `gen_ai.request.model` si présent dans la réponse). Réponse `text/event-stream` : aucune lecture, compteur `gen_ai.client.token.usage.non_mesure` (+1, attribut `appelant.azp`). Le corps relayé au client est identique (test).
- Meter enregistré dans la configuration OpenTelemetry existante de la gateway (métriques exportées comme les traces).

- [ ] Tests d'abord : métrique émise avec les bons nombres et attributs (collecteur de métriques en mémoire) ; aucun attribut contenant du texte du prompt ou de la réponse ; corps inchangé ; streaming → compteur `non_mesure`. Échec montré.
- [ ] Implémenter ; tests verts ; commit `feat(gateway): mesure des tokens LLM par appelant (#70)`.

### Task 3: rag appelle le LLM par la gateway

**Files:** `rag/agentinsurflow_rag/infrastructure/azure_openai/{config.py,llm.py,embeddings.py}`, tests `rag/tests/unit/test_llm.py`, `test_embeddings.py`, `.env.example`, `rag/README.md`, `docker-compose.yml` (rag : `AZURE_OPENAI_ENDPOINT=http://gateway:8000/api/llm`, `LLM_AUDIENCE`).

- `client_openai(cfg)` : `base_url = f"{cfg.azure_openai_endpoint.rstrip('/')}/v1/"` (l'endpoint est la gateway `…/api/llm`) ; `api_key` = fournisseur de jeton d'**application** pour `"{llm_audience}/.default"` : secret de l'inscription rag en local (`RAG_CLIENT_SECRET`, déjà utilisé par l'OBO de rag) sinon identité managée fédérée (même ordre que `rag/…/infrastructure/entra/obo.py`). **Plus de clé** : `azure_openai_api_key` supprimé de la configuration ; sans `llm_audience` ou sans identité → erreur explicite au démarrage du client (comme aujourd'hui sans endpoint).
- [ ] Tests d'abord : base_url, fournisseur de jeton (secret local puis identité managée, bonne portée), plus aucune clé lue, erreur sans audience. Échec montré.
- [ ] `uv run pytest rag/tests --no-cov -q` (hors le test daté connu `test_rejeu_instantane_n_appelle_pas_piste`), `make test`, `make lint` ; commit `feat(rag): LLM et embeddings par la gateway, jeton d'application, plus de clé (#70)`.

### Task 4: Container App rag, Foundry fermé, infra, déploiement, docs

**Files:** nouveau `infra/containerapp-rag.yaml` (conteneur rag, entrée interne port 8001, identité managée propre, `AZURE_OPENAI_ENDPOINT=${GATEWAY_URL}/api/llm`, `LLM_AUDIENCE`, OTLP par la gateway avec `TELEMETRIE_AUDIENCE`, accès PostgreSQL inchangé) ; `infra/containerapp.yaml` (retirer rag ; gateway : cluster `rag` → `https://${RAG_APP_FQDN}`, cluster `llm` → endpoint Foundry, `Llm__Portee`, audiences llm) ; `infra/bootstrap.sh` (Container Apps rag staging/production, entrée interne) ; `infra/entra.sh` (identité `uami-insurflow-rag-app` fédérée sur `agentinsurflow-rag`, rôle `Telemetrie` à rag ; la gateway garde `uami-insurflow-rag` — renommer seulement si sans risque, sinon documenter) ; nouveau `infra/llm.sh` (inscription `agentinsurflow-llm` + rôle `LLM` attribué à rag ; inscription `agentinsurflow-gateway-local` + secret affiché une fois pour le `.env` ; Foundry `disableLocalAuth=true` ; rôle « Cognitive Services OpenAI User » attribué à l'identité de la gateway et à `agentinsurflow-gateway-local`, **retiré** de toute autre identité listée) ; `Makefile` (cible `llm`) ; `.github/workflows/deploy.yml` (déploiement de la Container App rag, ordre justifié, garde-fous de variables, fumées `/health/rag` et `POST /api/llm/v1/chat/completions` sans jeton → 401) ; `docker-compose.yml` (gateway : `Gateway__ClientId`, `Gateway__ClientSecret`, cluster `llm`) ; docs : `docs/secrets.md`, `docs/rollback.md`, `README.md` (dont la ligne « trois images »), `gateway/README.md`, `rag/README.md`, spec MCP et spec calcul si elles décrivent rag dans la Container App principale.

- [ ] `bash -n` + `shellcheck` sur les scripts touchés ; `actionlint` ; YAML valides ; `make lint`, `make test`, `dotnet test gateway`.
- [ ] Commit `feat(infra): rag dans sa Container App, Foundry réservé à la gateway (#70)`.
