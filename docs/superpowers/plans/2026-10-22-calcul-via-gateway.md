# Calcul via la gateway — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Faire passer le canal serveur MCP → Function de calcul par la gateway (route, politique rôle + audience, débit), supprimer l'exception à D22.

**Architecture:** La gateway relaie le jeton application du serveur MCP (rôle `Calcul`, audience « calcul ») vers la Function, qui le revalide par Easy Auth. Le serveur MCP vise la gateway et demande toujours son jeton.

**Spec:** [`docs/superpowers/specs/2026-10-22-calcul-risque-prime-design.md`](../specs/2026-10-22-calcul-risque-prime-design.md) § 3.3 (amendement du 22/10).

## Global Constraints

- Branche `feat/RiskPrime`, commits locaux ; jamais de push sur `main`.
- Aucune nouvelle dépendance ni changement de version.
- `gateway/CLAUDE.md` : refus par défaut, chaque route déclare `AuthorizationPolicy` (rôle **et** audience) ; erreurs ProblemDetails (`NON_AUTHENTIFIE`, `ACCES_REFUSE`, `TROP_DE_REQUETES`).
- Aucun secret dans le dépôt ; scripts `infra/*.sh` rédigés, jamais lancés par un agent ; aucune commande `az`.
- Jamais dans une trace ou un log : faits, montants, `numero_contrat`, jeton.
- Exploration : graphify d'abord (`graphify query "<q>" --graph /Volumes/CodeSource/myRepos/simplon/certification/graphify-out/graph.json`).

---

### Task 1: Route `calcul` de la gateway

**Files:**
- Modify: `gateway/src/AgentInsurFlow.Gateway.Api/appsettings.Routes.json`, `gateway/src/AgentInsurFlow.Gateway.Api/Program.cs`, `gateway/src/AgentInsurFlow.Gateway.Api/appsettings.json` (si les audiences y sont déclarées), `docker-compose.yml` (service `gateway`), `infra/containerapp.yaml` (conteneur gateway), `gateway/README.md`
- Test: les tests WireMock existants de `gateway/tests/AgentInsurFlow.Gateway.Api.Tests/` (`RoutageTests`, `AutorisationTests`, `DebitTests`), même style

**Interfaces produites (consommées par la tâche 2) :**
- `POST /api/calcul/{**reste}` → cluster `calcul`, chemin réécrit `/api/{**reste}` (ex. `/api/calcul/evaluer` → `/api/evaluer`), en-tête `Authorization` relayé tel quel.
- Politique `calcul-mcp` : `RequireRole("Calcul")` + `RequireClaim("aud", audiencesCalcul)` ; audiences lues dans `Entra:Audiences:calcul` (même mécanisme `Audiences(service)`, ajoutées aux `ValidAudiences`).
- Limite de débit nommée `calcul` (fenêtre fixe, valeur cohérente avec `mcp`).
- `GET /health/calcul` anonyme, débit désactivé → `/api/sante` du cluster `calcul`.
- Destination du cluster `calcul` : `ReverseProxy__Clusters__calcul__Destinations__d1__Address` (compose : `http://calcul:80` ; Azure : `${CALCUL_URL}` = URL de la Function).

- [ ] Tests d'abord : routage (`/api/calcul/evaluer` arrive en `/api/evaluer` sur le WireMock, avec l'en-tête `Authorization`), 401 sans jeton, 403 jeton sans rôle `Calcul`, 403 rôle `Calcul` mais mauvaise audience, 429 au-delà de la limite, `/health/calcul` anonyme → `/api/sante`. Échec montré.
- [ ] Implémenter, `dotnet test gateway` vert, `dotnet format` propre.
- [ ] Compose (`Entra__Audiences__calcul__0`, adresse du cluster) et `infra/containerapp.yaml` (mêmes variables, `${CALCUL_AUDIENCE}`, `${CALCUL_URL}`) ; README de la gateway : la route et sa politique.
- [ ] Commit `feat(gateway): route calcul vers la Function (rôle Calcul + audience, débit) (T9 #64)`.

### Task 2: Serveur MCP via la gateway, infra et docs

**Files:**
- Modify: `serveur-mcp/agentinsurflow_mcp/infrastructure/fonction_calcul/client.py`, `serveur-mcp/tests/unit/test_client_calcul.py`, `docker-compose.yml` (service `serveur-mcp` : `CALCUL_URL: http://gateway:8000/api/calcul`, `CALCUL_AUDIENCE`), `infra/containerapp.yaml` (conteneur `serveur-mcp` : `CALCUL_URL` = `http://localhost:8000/api/calcul`), `.github/workflows/deploy.yml`, `infra/calcul.sh`, `.env.example`, `docs/secrets.md`, `docs/superpowers/specs/2026-10-21-serveur-mcp-design.md`, `serveur-mcp/README.md`, `fonction-calcul/README.md`

**Interfaces consommées :** celles de la tâche 1.

- [ ] Tests d'abord (`test_client_calcul.py`) : avec `calcul_audience` et `mcp_client_secret` (local) → jeton demandé par `ClientSecretCredential(tenant, mcp_api_client_id, secret)` pour `"{calcul_audience}/.default"` ; avec l'identité managée (Azure) → `ClientAssertionCredential` inchangé ; **sans `calcul_audience`** ou sans configuration Entra → `ErreurOutil(CALCUL_INDISPONIBLE)` **sans appel HTTP** (le jeton est désormais obligatoire). L'URL appelée est `{calcul_url}/evaluer` et `{calcul_url}/calculer` (la base inclut `/api/calcul`). Échec montré.
- [ ] Implémenter dans `client.py` (même ordre de priorité que `infrastructure/entra/obo.py` : secret local d'abord, puis identité managée) ; `uv run pytest serveur-mcp/tests --no-cov -q`, `make test`, `make lint` verts.
- [ ] `infra/calcul.sh` : rôle d'application `Calcul` (`allowedMemberTypes: ["Application"]`, id fixe en variable `CALCUL_ROLE`, comme `MCP_GESTIONNAIRE` dans `entra.sh`) sur l'inscription « calcul », attribué au principal de service de `MCP_API_CLIENT_ID` (motif `attribuer()`), et au principal de la CI si la fumée en a besoin (non : la fumée est anonyme). `bash -n` et `shellcheck` propres.
- [ ] `deploy.yml` : la fumée de la Function passe par la gateway **après** la mise à jour de la Container App : `GET $URL/health/calcul` → bonne version ; `POST $URL/api/calcul/evaluer` sans jeton → 401 (gateway). Garder la fumée directe existante (version + 401 Easy Auth) avant la mise à jour. `actionlint` sans nouvelle alerte.
- [ ] Docs : supprimer partout l'« exception à D22 » du calcul (spec MCP § 2, § 4, § 5.1, § 5.3, § 6 ; READMEs ; `docs/secrets.md`) et décrire le chemin MCP → gateway → Function ; `.env.example` (`CALCUL_ROLE=`).
- [ ] Commit `feat(mcp): appel de la Function de calcul par la gateway, jeton toujours requis (T9 #64)`.
