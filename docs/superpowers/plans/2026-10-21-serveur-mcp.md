# Serveur MCP (via la gateway) — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** un 5e conteneur Python qui expose en MCP (Streamable HTTP, SSE) les six outils de la V1 au cluster d'agents, derrière la gateway, avec une matrice d'accès par `azp`, l'On-Behalf-Of vers rag et underwriting-admin, et des traces sans donnée personnelle.

**Architecture:** underwriting-admin reçoit deux endpoints d'écriture (brouillon, statut) ; la gateway reçoit la route `/mcp` et les routes de ces écritures ; le serveur MCP (`serveur-mcp/`, hexagonal) valide le jeton, filtre `list_tools`/`call_tool` par `azp`, puis appelle rag et underwriting-admin **par la gateway** avec un jeton OBO. Les tâches 1 → 3 servent aussi au repli REST du 27/10 : elles passent en premier.

**Tech Stack:** Python 3.12, SDK MCP officiel (`mcp`, `FastMCP`), FastAPI/Starlette, PyJWT, azure-identity, httpx, OpenTelemetry ; .NET 10 (Minimal API, EF Core, xUnit, WireMock.Net), YARP.

**Spec:** `docs/superpowers/specs/2026-10-21-serveur-mcp-design.md` (issue #15).

## Global Constraints

- Contrat du monorepo `CLAUDE.md` et `underwriting-admin/CLAUDE.md` : Français partout ; aucun secret ; erreurs REST en ProblemDetails avec `code` ; JSON snake_case ; SQL paramétré ; migrations EF seulement (droits par `migrationBuilder.Sql`) ; BOLA : `gestionnaire_id` = claim `oid`, même 404 pour « absent » et « autre gestionnaire ».
- Écritures Azure/Entra : rédigées dans `infra/*.sh`, **lancées à la main par Acerola**, jamais par un agent.
- Aucun changement de version (`pyproject.toml`, `rag/pyproject.toml`). **Ajout de la dépendance `mcp` : version proposée à Acerola et validée avant `uv add`.**
- Branche `feat/mcp`, PR en brouillon, jamais de push sur `main`.
- Hexagonal (Python) : `domain/` et `application/` sans import externe, vérifié par test ; Clean Architecture (C#) : `Domain` sans NuGet.
- Tests selon `.claude/rules/testing-pyramid.md` : nommer le niveau (TU/TI/E2E) de chaque test ; couverture ≥ 80 % par projet.
- Codes d'erreur d'outil : `UNAUTHORIZED_TOOL`, `NOT_FOUND_IN_CORPUS`, `CONTRAT_INTROUVABLE`, `DOSSIERS_INDISPONIBLES` (+ `ARGUMENTS_INVALIDES`, choix de Claude, pour un 400/422 d'underwriting-admin).
- Jamais tracé : jeton, `numero_contrat`, identité du gestionnaire, texte d'une requête `search_rag` (seulement `question.sha256`, `question.longueur`), contenu de contrat, fiche ou prime.
- `evaluer_risque` et `calculer_prime` : **hors de ce plan** jusqu'à la réponse d'Acerola (tâche 9, bloquée).

## Review Focus

- Jeton valide mais `azp` absent de la matrice → `list_tools` vide et `call_tool` → `UNAUTHORIZED_TOOL`, sans appel backend (tâche 4).
- Écriture sur le contrat d'un autre gestionnaire → même 404 que « absent », aucune ligne modifiée (tâche 2), traduit en `CONTRAT_INTROUVABLE` (tâche 6).
- `enregistrer_brouillon` rejoué deux fois → une seule `Decision` brouillon et une seule `Prime` (idempotence D66, tâche 2).
- `update_statut_dossier` vers `ACCEPTE`/`REFUSE` sans `validation` → refus 400, rien écrit (tâche 1) : D9 tient même si le cluster a un bogue.
- Réponse SSE longue derrière la gateway → les événements arrivent au fil de l'eau, pas en bloc (tâche 3, test de flux).

---

## Structure des fichiers

```
underwriting-admin/src/
  …Domain/RèglesStatut.cs                      # statuts, validations, règle D9 (pur)
  …Application/IDepotEcritures.cs              # port d'écriture
  …Application/EnregistrerBrouillon.cs, ChangerStatut.cs
  …Infrastructure/Dossiers/DepotEcrituresEf.cs # adapter EF (filtre gestionnaire_id)
  …Infrastructure/Dossiers/Migrations/<horodatage>_DroitsEcriture.cs
  …Api/EcrituresEndpoints.cs
gateway/src/AgentInsurFlow.Gateway.Api/{Program.cs, appsettings.Routes.json}
gateway/tests/…/McpTests.cs
serveur-mcp/                                    # ⚠ pas « mcp/ » : masquerait le paquet `mcp` du SDK (pythonpath ".")
  pyproject.toml, Dockerfile, README.md
  agentinsurflow_mcp/
    domain/models.py      # Appelant, ErreurOutil, codes, Fiche, PrimeBrouillon
    domain/matrice.py     # MATRICE, outils_autorises, est_autorise
    domain/ports.py       # CorpusPort, DossiersPort, JetonsPort (Protocol)
    application/outils.py # un cas d'usage par outil
    infrastructure/entra/{jetons.py, obo.py}
    infrastructure/gateway/client.py   # ClientGateway : CorpusPort + DossiersPort
    infrastructure/otel/telemetrie.py
    api/{app.py, securite.py, serveur.py}
  tests/{unit,integration}/, tests/fakes.py, tests/jetons_de_test.py
```

`jetons.py`, `obo.py` et `telemetrie.py` sont **adaptés** de rag (copie courte, pas d'import de `agentinsurflow_rag` : le conteneur MCP n'embarque ni OpenAI ni SQLAlchemy). *ponytail: copie de ~120 lignes ; extraire un paquet commun si un 3e service Python apparaît.*

---

### Task 1: underwriting-admin — règles et cas d'usage d'écriture

**Files:**
- Create: `underwriting-admin/src/AgentInsurFlow.UnderwritingAdmin.Domain/ReglesStatut.cs`
- Create: `underwriting-admin/src/AgentInsurFlow.UnderwritingAdmin.Application/IDepotEcritures.cs`, `EnregistrerBrouillon.cs`, `ChangerStatut.cs`
- Test: `underwriting-admin/tests/…Domain.Tests/ReglesStatutTests.cs`, `…Application.Tests/EcrituresTests.cs` (TU)

**Interfaces:**
- Produces (Domain) :
  - `public static class ReglesStatut` : `Cibles = { "EN_ANALYSE", "REVUE_HUMAINE", "ACCEPTE", "REFUSE" }`, `Validations = { "VALIDEE", "CORRIGEE" }`, `Decisions = { "ACCEPTE", "REFUSE", "REVUE_HUMAINE" }`.
  - `public static string? Refus(string statutCible, string? validation)` → `null` si accepté, sinon le `code` : `STATUT_INCONNU`, `VALIDATION_EXIGEE` (cible `ACCEPTE`/`REFUSE` sans validation, D9), `VALIDATION_INCONNUE`, `VALIDATION_INATTENDUE` (validation sur `EN_ANALYSE`/`REVUE_HUMAINE`).
  - `public sealed record FicheBrouillon(string Decision, string ContratType, decimal Score, string VersionBareme, IReadOnlyList<string> RegleIds, IReadOnlyList<string> Motifs, IReadOnlyList<string> Citations)`.
  - `public sealed record PrimeBrouillon(decimal PrimeTtc, string Periodicite, DateOnly DateEffet)` (`Periodicite` ∈ `mensuelle`, `annuelle`).
  - `public sealed record ChangementStatut(string StatutCible, string? Validation, string? DecisionCorrigee)`.
- Produces (Application) :
  - `public interface IDepotEcritures { Task<bool> EnregistrerBrouillon(string gestionnaireId, string numeroContrat, FicheBrouillon fiche, PrimeBrouillon? prime, CancellationToken ct); Task<bool> ChangerStatut(string gestionnaireId, string numeroContrat, ChangementStatut changement, string auteur, CancellationToken ct); }` — `false` = contrat absent **ou** d'un autre gestionnaire.
  - `EnregistrerBrouillon(IDepotEcritures)` : `Task<ResultatEcriture> Executer(string gestionnaireId, string numeroContrat, FicheBrouillon fiche, PrimeBrouillon? prime, CancellationToken ct)`.
  - `ChangerStatut(IDepotEcritures)` : `Task<ResultatEcriture> Executer(string gestionnaireId, string numeroContrat, ChangementStatut changement, CancellationToken ct)` — applique `ReglesStatut.Refus` avant tout appel au port ; `auteur = gestionnaireId`.
  - `public sealed record ResultatEcriture(bool Ecrit, string? CodeRefus)` ; `Ecrit=false, CodeRefus=null` = introuvable (404).

- [ ] **Step 1: Write the failing tests** — `ReglesStatutTests` (Theory) : `("ACCEPTE", null) → "VALIDATION_EXIGEE"`, `("REFUSE", "VALIDEE") → null`, `("REVUE_HUMAINE", null) → null`, `("REVUE_HUMAINE", "VALIDEE") → "VALIDATION_INATTENDUE"`, `("ACCEPTE", "OK") → "VALIDATION_INCONNUE"`, `("actif", null) → "STATUT_INCONNU"`. `EcrituresTests` (port simulé) : `ChangerStatut_sans_validation_n_appelle_pas_le_depot`, `ChangerStatut_contrat_introuvable_rend_Ecrit_false_sans_code`, `EnregistrerBrouillon_decision_inconnue_refusee` (code `DECISION_INCONNUE`), `EnregistrerBrouillon_periodicite_inconnue_refusee` (code `PERIODICITE_INCONNUE`).
- [ ] **Step 2: Run** `make underwriting-test` → FAIL (types absents).
- [ ] **Step 3: Implement** les types ci-dessus.
- [ ] **Step 4: Run** `make underwriting-test` → PASS, `DependanceTests` toujours verts.
- [ ] **Step 5: Commit** `feat(underwriting): règles et cas d'usage d'écriture des dossiers (#15)`

### Task 2: underwriting-admin — adapter EF, droits SQL et endpoints d'écriture

**Files:**
- Create: `…Infrastructure/Dossiers/DepotEcrituresEf.cs`, `…Infrastructure/Dossiers/Migrations/<horodatage>_DroitsEcriture.cs` (via `dotnet ef migrations add DroitsEcriture`)
- Modify: `…Infrastructure/Dossiers/DossiersDbContext.cs` (DbSets `Contrats`, `Decisions`, `Primes`), `DossiersServices.cs` (`AddScoped<IDepotEcritures, DepotEcrituresEf>()`), `…Api/Program.cs` (`MapEcritures()`, cas d'usage en DI)
- Create: `…Api/EcrituresEndpoints.cs`
- Test: `…Infrastructure.Tests/EcrituresPostgresTests.cs` (TI, PostgreSQL du compose), `…Api.Tests/EcrituresTests.cs` (TI, `WebApplicationFactory`, port en mémoire)

**Interfaces:**
- Consumes: Task 1.
- Produces (HTTP, groupe `/api/contrats`, `RequireAuthorization("Gestionnaire")`, `oid` du jeton) :
  - `PUT /api/contrats/{numero_contrat}/brouillon` — corps `{ "fiche": {decision, contrat_type, score, version_bareme, regle_ids, motifs, citations}, "prime": {prime_ttc, periodicite, date_effet} | null }` → `204` ; `404 CONTRAT_INTROUVABLE` ; `400` avec le code de refus.
  - `PUT /api/contrats/{numero_contrat}/statut` — corps `{ "statut": "...", "validation": "VALIDEE"|"CORRIGEE"|null, "decision_corrigee": "ACCEPTE"|"REFUSE"|null }` → `204` ; `404 CONTRAT_INTROUVABLE` ; `400` avec le code.
- Comportement de `DepotEcrituresEf` :
  - toujours `WHERE numero_contrat = @n AND gestionnaire_id = @g` sur `contrat` ; aucune ligne → `false`, rien écrit ;
  - brouillon : **upsert** de la `Decision` en `etat_validation = 'brouillon'` du contrat (une seule ; rejouer remplace) et de la `Prime` (1 → 1, P18) ; `contrat.statut` inchangé ; `Auteur = "agent"`, `Horodatage = now` ;
  - statut : `contrat.statut = cible`, `mis_a_jour = now` ; si `validation` : la décision brouillon passe à `VALIDEE`/`CORRIGEE`, `Auteur = oid`, et `DecisionRendue = decision_corrigee` si `CORRIGEE`. Le tout dans une transaction.
- Migration `DroitsEcriture` (SQL) : `GRANT SELECT, UPDATE (statut, mis_a_jour) ON contrat TO dossiers; GRANT SELECT, INSERT, UPDATE ON decision, prime TO dossiers;` ; `Down` : les `REVOKE` correspondants. Aucune colonne ni table nouvelle.

- [ ] **Step 1: Write the failing tests** — `EcrituresPostgresTests` : `Brouillon_rejoue_deux_fois_une_seule_decision_et_une_seule_prime`, `Brouillon_contrat_d_un_autre_gestionnaire_rend_false_et_n_ecrit_rien`, `Statut_valide_passe_la_decision_a_VALIDEE_avec_auteur_oid`, `Statut_CORRIGEE_remplace_la_decision_rendue`, `Compte_dossiers_ne_peut_pas_modifier_le_souscripteur` (UPDATE `souscripteur` → `PostgresException` 42501). `EcrituresTests` (API) : `204` nominal, `404` même corps pour absent et autre gestionnaire, `400 VALIDATION_EXIGEE`, `401` sans jeton, `403` sans rôle, JSON snake_case accepté.
- [ ] **Step 2: Run** `make underwriting-test` (+ PostgreSQL du compose) → FAIL.
- [ ] **Step 3: Implement** adapter, migration, endpoints (`.WithName("EnregistrerBrouillon")`, `.WithName("ChangerStatut")`, `ProducesProblem(400/401/403/404)`).
- [ ] **Step 4: Run** `make underwriting-test` → PASS ; `make openapi` régénère `docs/openapi/underwriting-admin.json` (commité).
- [ ] **Step 5: Commit** `feat(underwriting): écritures brouillon et statut, BOLA et droits SQL (#15)`

### Task 3: gateway — routes d'écriture et route `/mcp`

**Files:**
- Modify: `gateway/src/AgentInsurFlow.Gateway.Api/appsettings.Routes.json`, `Program.cs`, `appsettings.json` (audiences `Entra:Audiences:mcp`), `gateway/README.md`
- Modify: `docker-compose.yml`, `infra/containerapp.yaml` (variables `Entra__Audiences__mcp__0/1`, `ReverseProxy__Clusters__mcp__…`)
- Test: `gateway/tests/AgentInsurFlow.Gateway.Api.Tests/McpTests.cs` (TI, WireMock.Net) ; `Backends` reçoit un 3e serveur `Mcp`

**Interfaces:**
- Produces :
  - les routes `underwriting-contrats` couvrent déjà `/api/contrats/{**reste}` : **vérifier par test** que `PUT …/brouillon` et `PUT …/statut` passent avec `underwriting-gestionnaire` (aucune route nouvelle si oui) ;
  - politique `mcp-gestionnaire` : `RequireRole("Gestionnaire").RequireClaim("aud", audiencesMcp)` ; `audiencesMcp = Audiences("mcp")`, ajoutées à `ValidAudiences` ;
  - limiteur `mcp` : `RateLimit:Mcp:PermitLimit`, défaut **60**/fenêtre (choix de Claude) ;
  - route `mcp` : `Match { Path: "/mcp", Methods: ["POST","GET","DELETE"] }`, `ClusterId: "mcp"`, `AuthorizationPolicy: "mcp-gestionnaire"`, `RateLimiterPolicy: "mcp"`, transform `X-Forwarded: Set` ; cluster `mcp` → `http://localhost:8003`, avec `HttpRequest: { "ActivityTimeout": "00:05:00" }` ;
  - pas de tampon : YARP ne met pas en tampon par défaut ; **vérifier** qu'aucun middleware (compression, `ResponseBuffering`) ne s'applique à `/mcp` ; `traceparent` relayé (comportement YARP par défaut).
- [ ] **Step 1: Write the failing tests** — `McpTests` : `Post_mcp_route_vers_le_backend_mcp` (corps et `Content-Type` relayés), `Get_mcp_route_vers_le_backend_mcp`, `Sans_jeton_401`, `Jeton_audience_rag_403`, `Sans_role_Gestionnaire_403`, `Au_dela_de_la_limite_429_RetryAfter`, `Sse_transmis_au_fil_de_l_eau` (WireMock répond `text/event-stream` avec deux événements séparés par un délai ; le client lit le 1er avant la fin du délai), `Traceparent_relaye`, `Put_brouillon_et_statut_routes_vers_underwriting`.
- [ ] **Step 2: Run** `make gateway-test` → FAIL.
- [ ] **Step 3: Implement** la configuration et la politique ; `gateway/README.md` : section « Exception JSON-RPC : `/mcp` » (pas d'OpenAPI ; outils, schémas renvoyés par `tools/list`, autorisation à deux niveaux, codes d'erreur — renvoi vers `serveur-mcp/README.md`).
- [ ] **Step 4: Run** `make gateway-test` → PASS.
- [ ] **Step 5: Commit** `feat(gateway): route /mcp en Streamable HTTP et écritures underwriting (#15)`

### Task 4: serveur MCP — socle, jeton, matrice d'accès

**Files:**
- Create: `serveur-mcp/pyproject.toml` (paquet `agentinsurflow-mcp`, version `0.1.0`, deps : `mcp` (version validée), `fastapi`, `uvicorn[standard]`, `pydantic-settings`, `azure-identity`, `pyjwt[crypto]`, `httpx`, `opentelemetry-*` comme rag)
- Modify: `pyproject.toml` racine (`members = ["rag", "serveur-mcp"]`, `tool.uv.sources`, `testpaths += "serveur-mcp/tests"`, `--cov=agentinsurflow_mcp`, `known-first-party`), `Makefile` (`lint` : `mypy serveur-mcp/agentinsurflow_mcp` ; `test` : `serveur-mcp/tests/unit`), `tools/pyramide.py` (dossiers `serveur-mcp/tests/unit` en TU, `serveur-mcp/tests/integration` en TI)
- Create: `domain/models.py`, `domain/matrice.py`, `domain/ports.py`, `infrastructure/entra/jetons.py`, `api/securite.py`, `api/serveur.py`, `api/app.py`
- Test: `tests/unit/test_architecture.py` (copie adaptée de rag), `tests/unit/test_matrice.py`, `tests/unit/test_jetons.py`, `tests/integration/test_protocole.py`, `tests/jetons_de_test.py`

**Interfaces:**
- Produces (domain) :
  - `Agent = Literal["orchestrateur", "redacteur", "actuaire"]`
  - `MATRICE: Mapping[Agent, frozenset[str]]` = orchestrateur → `{get_contrat, evaluer_risque, enregistrer_brouillon, update_statut_dossier}`, redacteur → `{search_rag}`, actuaire → `{calculer_prime}`.
  - `def outils_autorises(agent: Agent | None) -> frozenset[str]` ; `def est_autorise(agent: Agent | None, outil: str) -> bool` (agent `None` → rien).
  - `@dataclass(frozen=True) class Appelant: oid: str; azp: str; agent: Agent | None; roles: frozenset[str]; jeton: str` (`jeton` = assertion pour l'OBO, `repr=False`).
  - `class ErreurOutil(Exception): code: str` ; constantes `UNAUTHORIZED_TOOL`, `NOT_FOUND_IN_CORPUS`, `CONTRAT_INTROUVABLE`, `DOSSIERS_INDISPONIBLES`, `ARGUMENTS_INVALIDES`.
- Produces (infrastructure) : `ConfigAuth` (`azure_tenant_id`, `mcp_api_client_id`, `mcp_api_audiences`, `mcp_azp_orchestrateur`, `mcp_azp_redacteur`, `mcp_azp_actuaire`) ; `verifier_jeton(jeton, cle, cfg) -> Appelant` (comme rag ; `azp` lu de `azp` **ou** `appid` (jeton v1) ; agent = recherche de l'`azp` dans les trois variables).
- Produces (api) :
  - `securite.py` : middleware ASGI sur `/mcp` : pas de Bearer → `401 JETON_ABSENT` ; invalide → `401 JETON_INVALIDE` ; sans rôle `Gestionnaire` → `403 ROLE_MANQUANT` (ProblemDetails, comme rag) ; sinon `Appelant` dans un `ContextVar` `appelant_courant`.
  - `serveur.py` : `class ServeurMcp(FastMCP)` qui surcharge `list_tools()` (filtre par `outils_autorises(appelant_courant.get().agent)`) et `call_tool(name, arguments)` (refus `UNAUTHORIZED_TOOL` en `isError: true`, **avant** dispatch) ; `stateless_http=True` (spec § 4) ; `ErreurOutil` levée par un outil → résultat `isError: true`, `structuredContent = {"code": …}`, texte = message minimal.
  - `app.py` : `app = FastAPI()` avec `GET /health` (versions comme rag) et le montage de `serveur.streamable_http_app()` sur `/mcp` ; port **8003**.
- [ ] **Step 1: Write the failing tests** — `test_matrice` : chaque ligne de la matrice ; `est_autorise(None, "search_rag") is False` ; `est_autorise("redacteur", "update_statut_dossier") is False`. `test_jetons` : `azp` inconnu → `agent is None` ; jeton v1 (`appid`) reconnu ; audience rag refusée. `test_protocole` (TI, client MCP du SDK sur l'app en mémoire via `httpx.ASGITransport`) : `sans_jeton_401`, `role_manquant_403`, `redacteur_ne_voit_que_search_rag`, `azp_inconnu_liste_vide`, `redacteur_appelle_update_statut_dossier_UNAUTHORIZED_TOOL_sans_appel_backend` (port simulé qui échoue s'il est appelé). Outils de test enregistrés par le test (les vrais arrivent tâches 5–6).
- [ ] **Step 2: Run** `uv run pytest serveur-mcp/tests --no-cov` → FAIL.
- [ ] **Step 3: Demander à Acerola la version de `mcp`** à ajouter (proposer la dernière stable), puis `uv add --package agentinsurflow-mcp mcp==<version>`.
- [ ] **Step 4: Implement** ; vérifier dans le SDK installé le nom exact des méthodes surchargées (`FastMCP.list_tools`, `FastMCP.call_tool`) et l'enregistrement des handlers ; si la surcharge ne passe pas, enregistrer les handlers sur le `Server` bas niveau (`self._mcp_server.list_tools()` / `call_tool()`) dans `__init__`.
- [ ] **Step 5: Run** `make lint && uv run pytest serveur-mcp/tests` → PASS.
- [ ] **Step 6: Commit** `feat(mcp): socle hexagonal, jeton Entra et matrice d'accès par azp (#15)`

### Task 5: serveur MCP — OBO, client gateway, outils de lecture

**Files:**
- Create: `infrastructure/entra/obo.py`, `infrastructure/gateway/client.py`, `application/outils.py`
- Modify: `api/serveur.py` (enregistre `search_rag`, `get_contrat`)
- Test: `tests/unit/test_outils.py` (TU, ports simulés `tests/fakes.py`), `tests/unit/test_client_gateway.py` (TU, `httpx.MockTransport`), `tests/integration/test_outils_lecture.py` (TI)

**Interfaces:**
- Consumes: Task 4 (`Appelant`, `ErreurOutil`, `ServeurMcp`).
- Produces (ports) :
  - `class JetonsPort(Protocol): async def obo(self, appelant: Appelant, cible: Literal["rag", "underwriting"]) -> str` (lève `ErreurOutil(DOSSIERS_INDISPONIBLES)`).
  - `class CorpusPort(Protocol): async def chercher(self, jeton: str, question: str, top_k: int | None) -> dict[str, Any]` (le JSON `ResultatRechercheDTO` de rag ; `NOT_FOUND_IN_CORPUS` → `ErreurOutil`).
  - `class DossiersPort(Protocol): async def lire_contrat(self, jeton, numero_contrat) -> dict[str, Any]; async def enregistrer_brouillon(self, jeton, numero_contrat, corps: dict[str, Any]) -> None; async def changer_statut(self, jeton, numero_contrat, corps: dict[str, Any]) -> None` (404 → `CONTRAT_INTROUVABLE`, 400/422 → `ARGUMENTS_INVALIDES`, autre/transport → `DOSSIERS_INDISPONIBLES`).
- Produces (application) : `async def search_rag(appelant, jetons, corpus, question: str, top_k: int | None = None) -> dict` ; `async def get_contrat(appelant, jetons, dossiers, numero_contrat: str) -> dict`.
- `obo.py` : `ConfigObo` (`azure_tenant_id`, `mcp_api_client_id`, `rag_api_client_id`, `underwriting_api_client_id`, `gateway_url` défaut `http://localhost:8000`, `mcp_client_secret` local, `azure_uami_client_id`) ; portée `api://{client_id}/access_as_user` ; appel synchrone via `run_in_threadpool`.
- `ClientGateway` : `GET {gateway_url}/api/extraits?question=…&top_k=…`, `GET/PUT {gateway_url}/api/contrats/{quote(n)}[/brouillon|/statut]` ; `Authorization: Bearer <obo>` ; `traceparent` injecté (`propagate.inject`) ; clients httpx **non instrumentés** (comme rag).
- Docstrings (lues par le LLM du Rédacteur pour `search_rag`) : factuelles, disent ce que l'outil ne fait pas (« ne rédige aucune réponse », « renvoie NOT_FOUND_IN_CORPUS plutôt qu'un extrait hors sujet »).
- [ ] **Step 1: Write the failing tests** — `test_outils` : `search_rag` passe le jeton OBO `rag` ; `NOT_FOUND_IN_CORPUS` propagé ; `get_contrat` 404 → `CONTRAT_INTROUVABLE` ; OBO refusé → `DOSSIERS_INDISPONIBLES`. `test_client_gateway` : URL encodée (`AIF/1` → `AIF%2F1`), `traceparent` présent, 503 → `DOSSIERS_INDISPONIBLES`. `test_outils_lecture` (TI) : orchestrateur appelle `get_contrat` → résultat ; rédacteur appelle `search_rag` → résultat ; `isError` + `structuredContent.code` pour chaque code.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** `make lint && uv run pytest serveur-mcp/tests` → PASS.
- [ ] **Step 5: Commit** `feat(mcp): OBO par la gateway, outils search_rag et get_contrat (#15)`

### Task 6: serveur MCP — outils d'écriture

**Files:**
- Modify: `application/outils.py`, `api/serveur.py`
- Test: `tests/unit/test_outils.py`, `tests/integration/test_outils_ecriture.py`

**Interfaces:**
- Consumes: Task 5 (`DossiersPort`), Task 2 (corps HTTP).
- Produces : `async def enregistrer_brouillon(appelant, jetons, dossiers, numero_contrat: str, fiche: Fiche, prime: PrimeBrouillon | None = None) -> dict` ; `async def update_statut_dossier(appelant, jetons, dossiers, numero_contrat: str, statut: str, validation: str | None = None, decision_corrigee: str | None = None) -> dict`. `Fiche` et `PrimeBrouillon` : dataclasses du domaine (mêmes champs que Task 2) ; les arguments d'outil MCP sont typés par elles (schéma JSON produit par le SDK). Résultat : `{"ecrit": true}`.
- Le serveur MCP **ne vérifie pas** D9 : underwriting-admin le fait (Task 1) et son `400` revient en `ARGUMENTS_INVALIDES`.
- [ ] **Step 1: Write the failing tests** — corps envoyé à `PUT …/brouillon` en snake_case exact ; `update_statut_dossier("REVUE_HUMAINE")` sans validation passe ; `400` → `ARGUMENTS_INVALIDES` ; `404` → `CONTRAT_INTROUVABLE` ; TI : redacteur → `UNAUTHORIZED_TOOL` sur les deux.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(mcp): outils enregistrer_brouillon et update_statut_dossier (#15)`

### Task 7: serveur MCP — traces

**Files:**
- Create: `infrastructure/otel/telemetrie.py` (adapté de rag : `SERVICE = "agentinsurflow-mcp"`)
- Modify: `api/app.py` (instrumentation FastAPI sauf `/health`), `api/serveur.py`, `infrastructure/gateway/client.py`, `infrastructure/entra/obo.py`
- Test: `tests/integration/test_traces.py` (TI, `InMemorySpanExporter`)

**Interfaces:**
- Spans (spec § 7) : `mcp.lister_outils` (`appelant.azp`, `outils.nombre`) ; `mcp.outil` (`mcp.outil`, `appelant.azp`, `autorisation.decision` = `allow`|`deny`, `autorisation.regle` = `matrice:<agent>`|`matrice:inconnu`, `resultat.code` = `OK`|code, `isError`) ; `obo.echanger` (`obo.cible`, `obo.reussi`) ; `gateway.appel` (`http.route` gabarit sans valeur, `http.status_code`) ; écritures : `statut.cible`, `contrat.present` ; `search_rag` : `question.sha256`, `question.longueur`.
- [ ] **Step 1: Write the failing tests** — un appel par outil (et un refus) ; `test_aucune_donnee_personnelle_dans_les_spans` : aucun attribut ni événement ne contient le `numero_contrat`, le texte de la question, le jeton, l'`oid` ; `traceparent` entrant = même `trace_id` sur `mcp.outil` et sur l'en-tête sortant vers la gateway.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(mcp): traces OTLP sans donnée personnelle (#15)`

### Task 8: conteneur, Entra, déploiement, E2E et documentation

**Files:**
- Create: `serveur-mcp/Dockerfile` (calqué sur `rag/Dockerfile`, `--package agentinsurflow-mcp`, `EXPOSE 8003`, `USER nobody`, `CMD uvicorn agentinsurflow_mcp.api.app:app --host 0.0.0.0 --port 8003 --no-access-log`), `serveur-mcp/README.md`
- Modify: `docker-compose.yml` (service `serveur-mcp`, `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT: http://underwriting-admin:8002/v1/traces`, `GATEWAY_URL: http://gateway:8000`, cluster `mcp` de la gateway → `http://serveur-mcp:8003`), `infra/containerapp.yaml` (5e conteneur, `localhost:8002/v1/traces`, `GATEWAY_URL=http://localhost:8000`, sondes `/health:8003`, aucune entrée externe), `.github/workflows/ci-cd.yml` et `deploy.yml` (image `agentinsurflow-mcp:$SHA`, comme rag), `infra/entra.sh` (section ⑥ : inscription `agentinsurflow-mcp`, rôle `Gestionnaire`, portée `access_as_user`, permissions déléguées mcp → rag et mcp → underwriting `access_as_user`, consentement administrateur, identifiant fédéré de l'identité managée ; **écrit, pas lancé**), `.env.example` (variables `MCP_*` sans valeur), `e2e/test_parcours.py`
- Test: `e2e/test_parcours.py::test_mcp_liste_filtree_et_refus_type` (E2E, sauté sans jeton d'agent)

- [ ] **Step 1: Write the failing test** — E2E : `POST /mcp` `initialize` puis `tools/list` via la gateway avec un jeton de gestionnaire ; sans jeton → 401 ; `GET /health/mcp` → 200 (ajouter la route `mcp-sante` comme `rag-sante`).
- [ ] **Step 2: Run** `make up && make test-e2e` → FAIL.
- [ ] **Step 3: Implement** compose, Dockerfile, route santé ; `make up && make test-e2e` → PASS en local.
- [ ] **Step 4: Écrire** `infra/entra.sh` § ⑥ et `containerapp.yaml` ; **demander à Acerola de lancer `infra/entra.sh`** (et #47) ; ne rien lancer soi-même.
- [ ] **Step 5: Documentation** — `serveur-mcp/README.md` : architecture (diagramme Mermaid de la spec), catalogue des outils (paramètres, sortie, codes), matrice, authentification à deux niveaux, traces, exploitation ; titres hiérarchisés, tableaux avec en-têtes, texte alternatif des diagrammes (format accessible).
- [ ] **Step 6: Run** `make lint && make test-integration && make gateway-test && make underwriting-test && make pyramide` → PASS (pyramide informative).
- [ ] **Step 7: Commit** `feat(mcp): 5e conteneur, Entra, déploiement et documentation (#15)` ; ouvrir la PR en brouillon ; fumée verte après déploiement par la chaîne.

### Task 9 (bloquée) : `evaluer_risque` et `calculer_prime`

Bloquée jusqu'à la réponse d'Acerola (barème D28, formule D65). À sa réception : spec complétée (§ 5.3), puis une tâche sur le modèle de la tâche 5 (fonctions pures dans `domain/`, outils dans `application/outils.py`, TU sur des cas du barème et de la formule, TI d'autorisation : orchestrateur → `evaluer_risque`, actuaire → `calculer_prime`).
