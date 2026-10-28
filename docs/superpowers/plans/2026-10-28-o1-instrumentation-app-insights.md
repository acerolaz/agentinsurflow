# O1 — Instrumentation Application Insights — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Les 5 services (agentic-cluster, rag, serveur-mcp, gateway, underwriting-admin) et la Function de calcul envoient leurs traces, le journal `insurflow.audit` et Live Metrics vers une ressource App Insights par environnement. Ils gardent leur export OTLP vers le référentiel SQL (double export).

**Architecture:** L'exportateur se choisit par configuration :
- `APPLICATIONINSIGHTS_CONNECTION_STRING` présente : envoi vers App Insights ;
- `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` présente : envoi vers le référentiel SQL ;
- les deux : double export ;
- aucune : spans locaux seulement.

Côté Python, `configure_azure_monitor()` remplace la création manuelle du `TracerProvider`, avec ces réglages :
- l'exportateur OTLP existant est ajouté comme processeur supplémentaire ;
- **toutes** les instrumentations automatiques du distro sont désactivées (l'instrumentation FastAPI manuelle reste) ;
- la collecte des journaux est limitée à `insurflow.audit`.

Côté C#, `UseAzureMonitor()` s'ajoute au pipeline existant. Enfin, `infra/vigie.sh` (lancé à la main) crée les ressources et pose les secrets.

**Tech Stack:** Python 3 / FastAPI / OpenTelemetry SDK 1.45.1 / `azure-monitor-opentelemetry` 1.8.11 ; .NET 10 / OpenTelemetry 1.20.0 / `Azure.Monitor.OpenTelemetry.AspNetCore` 1.6.0 ; Azure CLI ; GitHub Actions.

**Spec:** [`docs/superpowers/specs/2026-10-28-o1-instrumentation-app-insights-design.md`](../specs/2026-10-28-o1-instrumentation-app-insights-design.md) (validée le 28/10). Découpage : [`2026-10-28-sprint5-sessions.md`](../specs/2026-10-28-sprint5-sessions.md). Issue #151 (chapeau #54 ; reprend #65 et #71).

## Global Constraints

- **Gel** : aucune fusion sur `main` du 29/10 au matin à la fin de la démo du 30/10. La PR S1 est fusionnée **après** le 30/10.
- Nouvelles dépendances accordées, versions figées : `azure-monitor-opentelemetry==1.8.11` (cluster, rag, serveur-mcp ; `uv.lock`), `Azure.Monitor.OpenTelemetry.AspNetCore` `1.6.0` (gateway, underwriting-admin). Aucune autre montée de version volontaire (OTel Python reste en 1.45.1 / 0.66b1, OTel .NET en 1.20.0) ; si `uv lock` ou NuGet impose une autre montée, **s'arrêter et demander**.
- Écritures Azure (ressources, secrets, réglages de la Function, variables GitHub) : **uniquement dans `infra/vigie.sh`, lancé à la main par Acerola**. Jamais par un agent ni par la CI.
- RGPD : jamais de nom, d'e-mail, de jeton, de prompt, de sortie de modèle ni de texte d'observation dans un attribut ou un journal exporté ; `enable_content_recording=False` conservé ; numéro de contrat interdit dans un chemin, une URL ou un nom de span HTTP. Il reste autorisé comme champ `numero_contrat` des journaux d'audit (D-V15).
- Une panne d'App Insights ou de l'export ne bloque ni ne ralentit jamais une réponse (export en lot, asynchrone).
- Hexagonal (Python) : `application/` et `domain/` n'importent ni OpenTelemetry ni le distro ; `audit.evaluation` passe par `AuditPort`.
- Vocabulaire : « Saga ». Commentaires et messages en français, au style du fichier modifié.
- Noms fixés :
  - ressources `appi-insurflow-staging` et `appi-insurflow-production` ;
  - workspace `workspace-svespucepZG6` ;
  - secret de Container App `appinsights-connection` ;
  - variable d'environnement `APPLICATIONINSIGHTS_CONNECTION_STRING` ;
  - journal `insurflow.audit` ;
  - messages `audit.agent`, `audit.evaluation`, `garde_fous.chargement`.

## Review Focus

1. **URL portant le numéro de contrat via une instrumentation automatique du distro** (httpx et requests dans rag et le MCP, HttpClient côté C#). On attend qu'aucun span de dépendance ne contienne `AIF-` → tests des tâches 1, 2 et 5.
2. **Journal racine capté par le distro** : un `logging.info` quelconque, qui pourrait contenir une donnée personnelle, ne doit jamais partir vers App Insights → test `logger_name` de la tâche 1.
3. **Secret `appinsights-connection` absent d'une Container App au déploiement**. On attend un échec clair de `deploy.yml` avant l'`update --yaml`, pas une révision cassée → porte de la tâche 6.
4. **Spans serveur en double côté C#** quand `UseAzureMonitor()` s'ajoute à l'`AddAspNetCoreInstrumentation` existant. On attend un seul span serveur par requête → test de la tâche 5.
5. **Évaluation qui échoue** (budget dépassé, MCP indisponible) : on attend une ligne `audit.evaluation` avec `statut_final = "ERREUR"`. Une requête refusée avant la Saga (404, 409) n'en produit pas → tests de la tâche 3.

---

### Task 1: Choix de l'exportateur dans le cluster (Python)

**Files:**
- Modify: `agentic-cluster/pyproject.toml` (ajout `azure-monitor-opentelemetry==1.8.11`), `uv.lock` (`uv lock`)
- Modify: `agentic-cluster/agentinsurflow_cluster/infrastructure/otel/telemetrie.py` (`configurer_telemetrie`)
- Test: `agentic-cluster/tests/unit/test_telemetrie_cluster.py`

**Interfaces:**
- Produces:
  - `INSTRUMENTATIONS_DISTRO_COUPEES: dict[str, dict[str, bool]]`, qui vaut `{nom: {"enabled": False}}` pour `azure_sdk`, `django`, `fastapi`, `flask`, `httpx`, `psycopg2`, `requests`, `urllib`, `urllib3`.
  - `configurer_telemetrie(version: str) -> None`, de signature inchangée.
  - Les tâches 2 et 4 recopient ce schéma.

- [ ] **Step 1: Write the failing tests** (le distro est remplacé par un espion via `monkeypatch` sur `telemetrie.configure_azure_monitor`)

```python
def test_sans_rien_aucun_export(monkeypatch, espion_azure):
    # ni APPLICATIONINSIGHTS_CONNECTION_STRING ni OTEL_EXPORTER_OTLP_*_ENDPOINT
    configurer_telemetrie("t")
    assert espion_azure.appels == []

def test_otlp_seul_garde_le_comportement_actuel(monkeypatch, espion_azure):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://x/v1/traces")
    configurer_telemetrie("t")
    assert espion_azure.appels == []
    # le TracerProvider global porte un BatchSpanProcessor(OTLPSpanExporter)

def test_app_insights_seul(monkeypatch, espion_azure):
    monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "InstrumentationKey=00000000-0000-0000-0000-000000000000")
    configurer_telemetrie("t")
    kw = espion_azure.appels[0]
    assert kw["span_processors"] == []
    assert kw["logger_name"] == "insurflow.audit"
    assert kw["enable_live_metrics"] is True
    assert kw["instrumentation_options"] == INSTRUMENTATIONS_DISTRO_COUPEES
    assert kw["resource"].attributes["deployment.environment"] == "local"

def test_double_export(monkeypatch, espion_azure):
    monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "InstrumentationKey=00000000-0000-0000-0000-000000000000")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://x/v1/traces")
    configurer_telemetrie("t")
    (proc,) = espion_azure.appels[0]["span_processors"]
    assert isinstance(proc.span_exporter, OTLPSpanExporter)

def test_toutes_les_instrumentations_du_distro_sont_coupees():
    assert {"httpx", "requests", "urllib3", "urllib", "fastapi"} <= INSTRUMENTATIONS_DISTRO_COUPEES.keys()
    assert all(v == {"enabled": False} for v in INSTRUMENTATIONS_DISTRO_COUPEES.values())
```

- [ ] **Step 2: Run them, they fail**

Run: `uv run pytest agentic-cluster/tests/unit/test_telemetrie_cluster.py -v`
Expected: FAIL (`INSTRUMENTATIONS_DISTRO_COUPEES` / `configure_azure_monitor` introuvables).

- [ ] **Step 3: Add the dependency, implement the switch**

`uv add --package agentinsurflow-cluster azure-monitor-opentelemetry==1.8.11` (vérifier : `uv.lock` garde `opentelemetry-sdk` en 1.45.1). Dans `configurer_telemetrie` :
- la ressource (`service.version`, `deployment.environment`) est construite comme aujourd'hui ;
- si `APPLICATIONINSIGHTS_CONNECTION_STRING` est présente : `configure_azure_monitor(resource=…, span_processors=[BatchSpanProcessor(creer_exportateur())] si un point OTLP est défini sinon [], logger_name="insurflow.audit", enable_live_metrics=True, instrumentation_options=INSTRUMENTATIONS_DISTRO_COUPEES)`. La chaîne est lue par le distro dans l'environnement ;
- sinon : le chemin actuel, inchangé.

Mettre à jour la docstring du module (« Application Insights viendra avec #54 » devient le tableau des 4 cas).

- [ ] **Step 4: Run tests, they pass**

Run: `uv run pytest agentic-cluster/tests/unit/test_telemetrie_cluster.py -v` puis `make lint`
Expected: PASS ; lint vert.

- [ ] **Step 5: Commit**

```bash
git add agentic-cluster/pyproject.toml uv.lock agentic-cluster/agentinsurflow_cluster/infrastructure/otel/telemetrie.py agentic-cluster/tests/unit/test_telemetrie_cluster.py
git commit -m "feat(cluster): export App Insights (#54) en plus de l'OTLP, instrumentations du distro coupées"
```

---

### Task 2: Même choix dans rag et serveur-mcp

**Files:**
- Modify: `rag/pyproject.toml`, `serveur-mcp/pyproject.toml`, `uv.lock`
- Modify: `rag/agentinsurflow_rag/infrastructure/otel/telemetrie.py`, `serveur-mcp/agentinsurflow_mcp/infrastructure/otel/telemetrie.py` (`configurer_telemetrie`)
- Test: les tests de télémétrie existants de chaque service (localiser avec `graphify query "test telemetrie rag"` / `"test_traces serveur-mcp"`), ou à défaut `rag/tests/unit/test_telemetrie.py`, `serveur-mcp/tests/unit/test_telemetrie.py`

**Interfaces:**
- Consumes: le schéma de la tâche 1. Chaque service garde **sa propre** constante `INSTRUMENTATIONS_DISTRO_COUPEES` : les paquets sont déployés séparément, sans module commun, comme aujourd'hui.
- Produces: `configurer_telemetrie(version: str) -> None`, de signature inchangée dans les deux services.

- [ ] **Step 1: Write the failing tests**. Ce sont les 4 cas de la tâche 1 et le test de la liste coupée, par service. En plus, le test qui protège l'invariant RGPD de ces deux services :

```python
def test_httpx_reste_non_instrumente(monkeypatch, espion_azure):
    monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "InstrumentationKey=00000000-0000-0000-0000-000000000000")
    configurer_telemetrie("t")
    assert espion_azure.appels[0]["instrumentation_options"]["httpx"] == {"enabled": False}
```

- [ ] **Step 2: Run, they fail** — `uv run pytest rag/tests serveur-mcp/tests -k telemetrie -v` → FAIL.
- [ ] **Step 3: Implement**. Même code que la tâche 1, chaque service gardant son `SERVICE` (`agentinsurflow-rag`, `agentinsurflow-mcp`) et sa configuration de jeton. rag configure sa télémétrie à l'import (`api/app.py:36`), ce qui reste ainsi.
- [ ] **Step 4: Run, they pass** — même commande + `make test` → PASS.
- [ ] **Step 5: Commit** — `feat(rag,mcp): export App Insights (#54) en plus de l'OTLP`.

---

### Task 3: `audit.evaluation`, une ligne par évaluation entrée dans la Saga

**Files:**
- Modify: `agentic-cluster/agentinsurflow_cluster/domain/ports.py` (`AuditPort`)
- Modify: `agentic-cluster/agentinsurflow_cluster/infrastructure/otel/audit.py` (`AuditOtel`, `CHAMPS`)
- Modify: `agentic-cluster/agentinsurflow_cluster/infrastructure/langgraph/graphe.py` (`ServiceEvaluation.__init__`, `ServiceEvaluation.evaluer`)
- Modify: `agentic-cluster/tests/fakes_cluster.py` (`FakeAudit`)
- Test: `agentic-cluster/tests/unit/test_evaluation.py`, `agentic-cluster/tests/unit/test_telemetrie_cluster.py`

**Interfaces:**
- Produces:
  - `AuditPort.evaluation(self, numero_contrat: str, statut_final: str, cause: str | None, duree_ms: int) -> Awaitable[None]` (méthode `async`).
  - `FakeAudit.evaluations: list[tuple[str, str, str | None]]` : (`numero_contrat`, `statut_final`, `cause`).
  - `CHAMPS` gagne `"statut_final"`.
  - Une ligne JSON `{"message": "audit.evaluation", "trace_id", "numero_contrat", "statut_final", "cause", "duree_ms", …}`, exportée par le journal `insurflow.audit` (donc vers `AppTraces` grâce à la tâche 1).

- [ ] **Step 1: Write the failing tests** (fakes du cluster ; noms à adapter aux fixtures de `test_evaluation.py`)

```python
async def test_evaluation_nominale_trace_son_statut_final(service, audit):
    r = await service.evaluer("AIF-2026-000001", "jeton", "oid-a")
    assert audit.evaluations == [("AIF-2026-000001", r.statut, r.etat.cause)]

async def test_budget_depasse_sans_conclusion_trace_erreur(service_lent, audit):
    with pytest.raises(DelaiDepasse):
        await service_lent.evaluer("AIF-2026-000001", "jeton", "oid-a")
    assert audit.evaluations == [("AIF-2026-000001", "ERREUR", "delai_depasse")]

async def test_mcp_indisponible_trace_erreur_avec_le_code(service_mcp_ko, audit):
    with pytest.raises(ErreurOutil):
        await service_mcp_ko.evaluer("AIF-2026-000001", "jeton", "oid-a")
    assert audit.evaluations == [("AIF-2026-000001", "ERREUR", "MCP_INDISPONIBLE")]

async def test_refus_avant_la_saga_ne_trace_rien(service, audit):
    # dossier d'un autre gestionnaire (404 BOLA) puis double clic (409)
    ...
    assert audit.evaluations == []

def test_ligne_audit_evaluation_sans_donnee_personnelle(capture_journal):
    asyncio.run(AuditOtel().evaluation("AIF-2026-000001", "REVUE_HUMAINE", "llm_ko", 9876))
    ligne = json.loads(capture_journal.lignes[0])
    assert ligne["message"] == "audit.evaluation"
    assert (ligne["statut_final"], ligne["cause"], ligne["duree_ms"]) == ("REVUE_HUMAINE", "llm_ko", 9876)
    assert set(ligne) <= {"message", *CHAMPS}
```

- [ ] **Step 2: Run, they fail** — `uv run pytest agentic-cluster/tests/unit/test_evaluation.py agentic-cluster/tests/unit/test_telemetrie_cluster.py -v` → FAIL (`evaluation` absent).
- [ ] **Step 3: Implement**
  - `AuditPort.evaluation` est documenté : « une ligne par évaluation entrée dans la Saga ; jamais de contenu ».
  - `AuditOtel.evaluation` écrit `journal.info("audit.evaluation", extra={…})` avec `trace_id_courant()` et les mêmes clés que `CHAMPS`, celles qui ne s'appliquent pas valant `None`. Aucun span supplémentaire : celui de la requête HTTP existe déjà.
  - `ServiceEvaluation` garde `self._audit = deps.audit`.
  - Dans `evaluer`, la mesure couvre ce qui suit les contrôles du verrou (après `DossierDecide`), jusqu'au `return` :
    - succès : `statut_final = resultat.statut`, `cause = resultat.etat.cause` ;
    - `DelaiDepasse` : `"ERREUR"` et `"delai_depasse"` ;
    - `ErreurOutil` : `"ERREUR"` et son code (`args[0]`) ;
    - toute autre exception : `"ERREUR"` et `None`.

    L'émission se fait dans un `finally` ; on ne capture jamais `Exception` sans la relancer.
  - `FakeAudit.evaluation` ajoute le tuple à `self.evaluations`.
- [ ] **Step 4: Run, they pass** — même commande, puis `make test-integration` (cluster) → PASS.
- [ ] **Step 5: Commit** — `feat(cluster): audit.evaluation, une ligne par évaluation (D-V7, A7)`.

---

### Task 4: `garde_fous.chargement` au démarrage du cluster

**Files:**
- Modify: `agentic-cluster/agentinsurflow_cluster/infrastructure/otel/audit.py` (ajout `journaliser_chargement_garde_fous`)
- Modify: `agentic-cluster/agentinsurflow_cluster/api/app.py` (`_assembler` : chronométrer `await asyncio.to_thread(ScannersLlmGuard)`)
- Test: `agentic-cluster/tests/unit/test_telemetrie_cluster.py`

**Interfaces:**
- Produces:
  - `journaliser_chargement_garde_fous(chargement_ms: int) -> None`, qui écrit `{"message": "garde_fous.chargement", "chargement_ms": …}` sur `insurflow.audit` ;
  - `CHAMPS` gagne `"chargement_ms"`.

- [ ] **Step 1: Failing test**

```python
def test_chargement_des_garde_fous_journalise(capture_journal):
    journaliser_chargement_garde_fous(6123)
    ligne = json.loads(capture_journal.lignes[0])
    assert (ligne["message"], ligne["chargement_ms"]) == ("garde_fous.chargement", 6123)
```

- [ ] **Step 2: Run, fails** — `uv run pytest agentic-cluster/tests/unit/test_telemetrie_cluster.py -k chargement -v`.
- [ ] **Step 3: Implement**. Utiliser `time.perf_counter()` autour du chargement dans `_assembler`, puis un appel unique. `journaliser_chargement_garde_fous` vit dans `infrastructure/otel/audit.py`, et `api/app.py` l'importe comme il importe déjà `AuditOtel`.
- [ ] **Step 4: Run, passes** — même commande + `make lint`.
- [ ] **Step 5: Commit** — `feat(cluster): durée de chargement des garde-fous (garde_fous.chargement)`.

---

### Task 5: Gateway et underwriting-admin — `UseAzureMonitor()` et masquage du numéro de contrat (#65)

**Files:**
- Modify: `gateway/src/AgentInsurFlow.Gateway.Api/AgentInsurFlow.Gateway.Api.csproj`, `underwriting-admin/src/AgentInsurFlow.UnderwritingAdmin.Api/AgentInsurFlow.UnderwritingAdmin.Api.csproj` (`Azure.Monitor.OpenTelemetry.AspNetCore` `1.6.0`)
- Modify: `gateway/src/AgentInsurFlow.Gateway.Api/Program.cs:191-216`, `underwriting-admin/src/AgentInsurFlow.UnderwritingAdmin.Api/Program.cs:110-123`
- Create: `gateway/src/AgentInsurFlow.Gateway.Api/MasquageNumero.cs`, `underwriting-admin/src/AgentInsurFlow.UnderwritingAdmin.Api/MasquageNumero.cs`. Il y a une copie par service, car les deux solutions sont indépendantes (voir l'Architecture).
- Test: `gateway/tests/AgentInsurFlow.Gateway.Api.Tests/TelemetrieTests.cs`, `underwriting-admin/tests/AgentInsurFlow.UnderwritingAdmin.Api.Tests/TracesTests.cs` (ajouts)

**Interfaces:**
- Produces: `static class MasquageNumero` avec :
  - `string Masquer(string texte)`, qui remplace chaque `AIF-\d{4}-\d{6}` par `{numero_contrat}` ;
  - `void Appliquer(Activity activite)`, qui masque `url.path`, `url.full`, `url.query`, `http.target` et `DisplayName` s'ils sont présents.

  `Appliquer` est branché sur `EnrichWithHttpRequest` et `EnrichWithHttpResponse` (AspNetCore), ainsi que sur `EnrichWithHttpRequestMessage` (HttpClient).
- `UseAzureMonitor()` n'est appelé que si `builder.Configuration["APPLICATIONINSIGHTS_CONNECTION_STRING"]` n'est pas vide ; l'`AddOtlpExporter` existant est conservé tel quel.

- [ ] **Step 1: Failing tests** (xUnit, `WebApplicationFactory` existant, exportateur en mémoire `OpenTelemetry.Exporter.InMemory` **seulement si déjà référencé** par les tests ; sinon un `ActivityListener` sur la source `Microsoft.AspNetCore`)

```csharp
[Fact] public void Masquer_remplace_le_numero() =>
    Assert.Equal("/v1/souscriptions/{numero_contrat}/evaluation",
        MasquageNumero.Masquer("/v1/souscriptions/AIF-2026-000001/evaluation"));

[Fact] public async Task Span_serveur_sans_numero_de_contrat()
{ /* GET /api/contrats/AIF-2026-000001 → toutes les activités capturées :
     aucune valeur de tag ni DisplayName ne contient "AIF-" */ }

[Fact] public async Task Avec_chaine_app_insights_un_seul_span_serveur_par_requete()
{ /* APPLICATIONINSIGHTS_CONNECTION_STRING=InstrumentationKey=00000000-0000-0000-0000-000000000000
     → une requête = exactement 1 activité Kind=Server */ }
```

- [ ] **Step 2: Run, they fail**
  - Run: `dotnet test gateway/AgentInsurFlow.Gateway.slnx` et la solution d'underwriting-admin.
  - Expected: FAIL (`MasquageNumero` introuvable).
- [ ] **Step 3: Implement**
  - Ajouter le paquet. Si `dotnet restore` en mode verrouillé impose une montée d'un paquet OpenTelemetry déjà référencé, **s'arrêter et demander**.
  - Ajouter `MasquageNumero` et le brancher sur les enrichissements, sans perdre `client.address` à la gateway.
  - Ajouter `UseAzureMonitor()` sous condition. Si le test des spans en double échoue, régler les options d'instrumentation partagées par `ConfigureOpenTelemetryTracerProvider` ; **ne pas** retirer l'instrumentation existante, qui porte les filtres `/health` et `/v1/traces`.
- [ ] **Step 4: Run, they pass** — mêmes commandes + `make test` → PASS.
- [ ] **Step 5: Commit** — `feat(gateway,underwriting): export App Insights (#54) et numéro de contrat masqué dans les spans HTTP (#65)`.

---

### Task 6: Infra — `infra/vigie.sh` (étape App Insights), YAML, porte de `deploy.yml`

**Files:**
- Create: `infra/vigie.sh`
- Modify: `Makefile`. Ajouter la cible `vigie:  ## make vigie ENV=staging|production : App Insights (#54), à la main`, qui lance `bash infra/vigie.sh $(ENV)`. Corriger aussi le commentaire de `up:`, qui doit lister les 7 services.
- Modify: `infra/containerapp.yaml`, `infra/containerapp-cluster.yaml`, `infra/containerapp-rag.yaml`, `infra/containerapp-mcp.yaml`, `infra/containerapp-underwriting.yaml`. Ajouter à chaque conteneur applicatif `- { name: APPLICATIONINSIGHTS_CONNECTION_STRING, secretRef: appinsights-connection }`.
- Modify: `.github/workflows/deploy.yml`. Ajouter une porte bloquante (lecture seule) avant chaque `az containerapp update --yaml` des 5 apps : le secret `appinsights-connection` doit exister, sinon `::error::secret appinsights-connection absent de $APP (lancer make vigie ENV=<env>)`. C'est le modèle du contrôle `checkpoint-dsn` (l. 328).
- Test: `tests/unit/test_vigie.py`

**Interfaces:**
- Produces: `make vigie ENV=staging|production`, idempotent (`existe … ||`, comme `bootstrap.sh`). Il lit le `.env` comme `postgres-annexe.sh`, avec les variables suivantes :
  - `AZURE_RESOURCE_GROUP`, `AZURE_LOCATION` ;
  - `APP_<ENV>`, `CLUSTER_APP_<ENV>`, `RAG_APP_<ENV>`, `MCP_APP_<ENV>`, `UW_APP_<ENV>`, `CALCUL_APP_<ENV>` ;
  - `LOG_ANALYTICS_WORKSPACE` (valeur à documenter : `workspace-svespucepZG6`).
- S2 étendra ce script après l'étape ③.

- [ ] **Step 1: Failing test** (modèle : `tests/unit/test_d22.py`)

```python
APPS = ["containerapp.yaml", "containerapp-cluster.yaml", "containerapp-rag.yaml",
        "containerapp-mcp.yaml", "containerapp-underwriting.yaml"]

@pytest.mark.parametrize("fichier", APPS)
def test_chaque_app_lit_la_chaine_app_insights_par_secret(fichier):
    modele = yaml.safe_load((RACINE / "infra" / fichier).read_text())
    for c in modele["properties"]["template"]["containers"]:
        assert {"name": "APPLICATIONINSIGHTS_CONNECTION_STRING", "secretRef": "appinsights-connection"} in c["env"]

def test_deploy_verifie_le_secret_avant_chaque_update():
    texte = (RACINE / ".github/workflows/deploy.yml").read_text()
    assert texte.count('index("appinsights-connection")') == 5

def test_vigie_refuse_un_env_inconnu():
    r = subprocess.run(["bash", str(RACINE / "infra/vigie.sh"), "recette"], capture_output=True, text=True)
    assert r.returncode != 0 and "staging|production" in r.stdout + r.stderr
```

- [ ] **Step 2: Run, fails** — `uv run pytest tests/unit/test_vigie.py -v` → FAIL.
- [ ] **Step 3: Implement `infra/vigie.sh`** (`set -euo pipefail`, en-tête « lancé À LA MAIN par Acerola, jamais par un agent ni la CI ») :
  - **⓪** contrôle `ENV` ∈ `staging|production` *avant* toute lecture du `.env` (le test l'exige) ;
  - **①** `az monitor app-insights component create --app appi-insurflow-$env --workspace <id de LOG_ANALYTICS_WORKSPACE> --kind web --application-type web`, si la ressource n'existe pas ;
  - **②** lecture de la chaîne de connexion, puis `az containerapp secret set --secrets appinsights-connection=<chaîne>` sur les 5 apps ;
  - **③** `az functionapp config appsettings set -n $CALCUL_APP_<ENV> --settings APPLICATIONINSIGHTS_CONNECTION_STRING=<chaîne>` ;
  - **④** récapitulatif, sans afficher la chaîne. Il rappelle que les anciens composants `acerolaz-calcul-<env>` sont conservés.

  Ajouter `LOG_ANALYTICS_WORKSPACE` au `.env.example` s'il existe.
- [ ] **Step 4: Run, passes** — même commande + `make test` → PASS.
- [ ] **Step 5: Commit** — `feat(infra): make vigie (App Insights par environnement), secret appinsights-connection exigé au déploiement`.

---

### Task 7: Documentation — D-V2 amendée, catalogue, README

**Files:**
- Modify: `docs/donnees/traces.md` (D-V2 amendée : le référentiel SQL sert l'espace gestionnaire, l'E2E et le local ; App Insights sert la vigie ; double export en Azure)
- Modify: `docs/contrat-personnel.md` §4 (« Émis aujourd'hui » : ajouter `audit.evaluation`, `garde_fous.chargement` ; KQL toujours marquées « à valider » jusqu'à la tâche 8)
- Modify: `README.md` (ligne « Santé » / observabilité : App Insights par environnement, `make vigie`)
- Modify: `docs/secrets.md` (secret `appinsights-connection` : qui le pose, où il est lu)

- [ ] **Step 1: Write the four changes.** Une phrase par fait, chaque fait sourcé dans la spec. Aucun seuil.
- [ ] **Step 2: Verify** — `uv run pytest tests/unit -v` (aucun test de doc cassé) ; relire les liens relatifs.
- [ ] **Step 3: Commit** — `docs: vigie S1 — D-V2 amendée, audit.evaluation, make vigie, secret appinsights-connection`.

---

### Task 8: Mise en service et preuves (staging puis production)

À faire **après le 30/10**. Les commandes `make vigie` et la fusion sont lancées **par Acerola**. L'agent prépare les requêtes et rédige les preuves.

**Files:**
- Create: `eval/preuves/kql-<date>-staging.md`
- Create: `infra/vigie/kql/` : une requête par fichier, validée. Fichiers : `latence_agent.kql`, `latence_evaluation.kql`, `jetons_agent.kql`, `jetons_gateway.kql`, `revue_humaine_par_cause.kql`, `refus_garde_fous.kql`, `llm_ko.kql`, `mcp_indisponible.kql`, `rgpd_champs_interdits.kql`. C'est la source unique que S2 réutilisera.
- Modify: `docs/contrat-personnel.md` §4 (KQL remplacées par les versions validées ; K2 et K9 mis à jour avec la preuve)

- [ ] **Step 1 (Acerola) :** `make vigie ENV=staging`, puis vérifier que le secret existe sur les 5 apps.
- [ ] **Step 2 (Acerola) :** fusionner la PR. `ci-cd.yml` déploie le staging et les evals passent (p95 ≤ 30 s, réussite ≥ 80 %) ; noter la p95 et la comparer aux 14,9 s du 27/10.
- [ ] **Step 3 :** une évaluation nominale et une évaluation `llm-off`. Lancer `make recette ACTION=llm-off`, faire l'évaluation, puis `make recette ACTION=llm-on`.
- [ ] **Step 4 : exécuter chaque requête** dans le Log Analytics `workspace-svespucepZG6`, filtrée par `_ResourceId` de `appi-insurflow-staging`. Corriger les noms de colonnes (`Properties`, `AppDependencies` pour `invoke_agent`). Enregistrer chaque version validée dans `infra/vigie/kql/`.
- [ ] **Step 5 : vérifications attendues**
  - Application Map : gateway, agentic-cluster, serveur-mcp, rag, underwriting-admin et Function **reliés** ;
  - Transaction Diagnostics : une évaluation sous un seul `operation_Id` ;
  - Live Metrics : le cluster visible pendant une évaluation ;
  - `audit.evaluation` présent pour les deux évaluations (`REVUE_HUMAINE` / `llm_ko` pour la seconde) ;
  - `rgpd_champs_interdits.kql` (motifs : `@`, `AIF-` dans `Url`, `Name`, `Target` et `Data` des requêtes et dépendances, champs de prompt) ne remonte rien ;
  - preuve D-V8 : la Σ journalière des attributs `gen_ai.usage.*` de la gateway (route `/api/llm`) moins la Σ `tokens_entree + tokens_sortie` d'`audit.agent` donne l'écart dû à rag, ce qui clôt #71 ;
  - le panneau « Outils appelés » de l'espace et l'E2E de la CI restent verts.
- [ ] **Step 6 :** rédiger `eval/preuves/kql-<date>-staging.md` (requêtes, résultats, captures avec texte alternatif) et mettre à jour le §4 du contrat, ainsi que K2 et K9.
- [ ] **Step 7 (Acerola) :** `make vigie ENV=production`, approbation de la production, puis les preuves Application Map, Live Metrics et KQL rejouées en production et ajoutées au fichier de preuve.
- [ ] **Step 8 : Commit** — `docs(preuves): App Insights en staging et production, KQL validées (K2, K9, #71)`.
