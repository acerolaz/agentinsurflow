# Calcul via la gateway — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Faire passer le canal serveur MCP → Function de calcul par la gateway, qui échange le jeton (la Function n'accepte que la gateway), et sortir le serveur MCP dans sa propre Container App ; supprimer l'exception à D22.

**Architecture:** La gateway valide le jeton application du serveur MCP (rôle `Calcul`, audience « calcul »), le remplace par le sien (`Azure.Identity`, identité managée) et relaie vers la Function, dont l'Easy Auth n'accepte que la gateway. Le serveur MCP a sa Container App (entrée interne, identité managée propre).

**Spec:** [`docs/superpowers/specs/2026-10-22-calcul-risque-prime-design.md`](../specs/2026-10-22-calcul-risque-prime-design.md) § 3.3 (amendement du 22/10).

## Global Constraints

- Branche `feat/RiskPrime`, commits locaux ; jamais de push sur `main`.
- Seule dépendance ajoutée, validée par Acerola le 22/10 : `Azure.Identity` (dernière version stable) dans la gateway. Rien d'autre.
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

### Task 2: Échange de jeton dans la gateway

**Files:** `gateway/src/AgentInsurFlow.Gateway.Api/AgentInsurFlow.Gateway.Api.csproj` (`Azure.Identity`), `Program.cs` (transformation YARP sur la route `calcul`), `appsettings.json`, tests `gateway/tests/…/CalculTests.cs`, `gateway/README.md`.

**Interfaces :**
- Configuration `Calcul:Portee` (ex. `api://<appId calcul>/.default`) et `Calcul:IdentiteClientId` (client id de l'identité managée de la Container App de la gateway). Portée absente → la gateway **retire** l'en-tête `Authorization` avant de relayer (local).
- Sur la route `calcul` seulement : après validation de la politique `calcul-mcp`, `Authorization: Bearer <jeton de la gateway>` remplace celui du MCP. Jeton obtenu par une abstraction injectée (interface `IJetonsSortants` ou `TokenCredential` d'`Azure.Identity` enregistré en singleton : `ManagedIdentityCredential(clientId)`), pour que les tests la remplacent par un faux.
- Échec d'obtention du jeton → 502 ProblemDetails, code `CALCUL_INDISPONIBLE`, sans détail du jeton.

- [ ] Tests d'abord (WireMock) : le backend reçoit le jeton **de la gateway** (faux credential), jamais celui du MCP ; sans portée configurée, aucun `Authorization` relayé ; autres routes inchangées (le jeton entrant y est relayé tel quel) ; credential en échec → 502 `CALCUL_INDISPONIBLE`. Échec montré.
- [ ] Implémenter ; `dotnet test gateway`, `dotnet format --verify-no-changes`.
- [ ] Commit `feat(gateway): échange de jeton vers la Function de calcul (Azure.Identity) (T9 #64)`.

### Task 3: Serveur MCP via la gateway (code)

**Files:** `serveur-mcp/agentinsurflow_mcp/infrastructure/fonction_calcul/client.py`, `serveur-mcp/agentinsurflow_mcp/infrastructure/otel/telemetrie.py`, tests `serveur-mcp/tests/unit/test_client_calcul.py` (+ test de l'exportateur), `docker-compose.yml` (`serveur-mcp` : `CALCUL_URL: http://gateway:8000/api/calcul`, `CALCUL_AUDIENCE`), `serveur-mcp/README.md`.

- [ ] Tests d'abord (`test_client_calcul.py`) : avec `calcul_audience` et `mcp_client_secret` (local) → `ClientSecretCredential(tenant, mcp_api_client_id, secret)` pour `"{calcul_audience}/.default"` ; avec l'identité managée (Azure) → `ClientAssertionCredential` inchangé ; **sans `calcul_audience`** ou sans configuration Entra → `ErreurOutil(CALCUL_INDISPONIBLE)` **sans appel HTTP**. URL appelée : `{calcul_url}/evaluer`, `{calcul_url}/calculer` (la base inclut `/api/calcul`). Échec montré.
- [ ] Exportateur OTLP : quand `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` vise la gateway et que `TELEMETRIE_AUDIENCE` est défini, chaque export porte `Authorization: Bearer <jeton d'application, audience underwriting, rôle Telemetrie>` (même credential : secret local ou identité managée) ; sans `TELEMETRIE_AUDIENCE`, comportement actuel. Test : l'en-tête est posé, le jeton n'est jamais journalisé ni tracé.
- [ ] `uv run pytest serveur-mcp/tests --no-cov -q`, `make test`, `make lint` verts. Commit `feat(mcp): calcul et traces par la gateway, jeton d'application toujours requis (T9 #64)`.

### Task 4: Container App du serveur MCP, infra, déploiement et docs

**Files:** `infra/containerapp.yaml` (retirer le conteneur `serveur-mcp` ; gateway : adresse du cluster `mcp` = `https://${MCP_APP_FQDN}` interne, `Calcul__Portee`, `Calcul__IdentiteClientId`), nouveau `infra/containerapp-mcp.yaml` (conteneur `serveur-mcp`, entrée **interne** port 8003, identité managée propre, `GATEWAY_URL`, `CALCUL_URL`, `CALCUL_AUDIENCE`, `TELEMETRIE_AUDIENCE`, OTLP vers `${GATEWAY_URL}/v1/traces`), `infra/bootstrap.sh` (Container Apps MCP staging et production, entrée interne), `infra/entra.sh` (identité managée du MCP, fédérée sur `agentinsurflow-mcp` à la place de l'identité partagée ; rôle `Telemetrie` d'underwriting attribué au MCP), `infra/calcul.sh` (rôle `Calcul` attribué au MCP ; Easy Auth `allowedApplications` = client id de l'identité managée de la **gateway**), `.github/workflows/deploy.yml` (déploie la Container App MCP puis la principale ; fumées `/health/mcp` et `/health/calcul` par la gateway ; `POST /api/calcul/evaluer` sans jeton → 401 ; la fumée directe de la Function reste), `.env.example`, `docs/secrets.md` (nouvelles variables par environnement : `MCP_APP_NAME`, `MCP_APP_FQDN`, `AZURE_UAMI_MCP_CLIENT_ID`, …), spec MCP (`2026-10-21-serveur-mcp-design.md` : plus de « 5e conteneur » ni d'exception à D22 pour le calcul), READMEs.

- [ ] Scripts : `bash -n`, `shellcheck` propres ; aucun lancé, aucune commande `az`.
- [ ] `actionlint .github/workflows/deploy.yml` sans nouvelle alerte ; `make lint`, `make test` verts.
- [ ] Commit `feat(infra): serveur MCP dans sa Container App, Function réservée à la gateway (T9 #64)`.
