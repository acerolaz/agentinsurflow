# O8 — Suppression de D26 (points de reprise par la gateway) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** la Saga n'a plus aucun accès à PostgreSQL ; ses points de reprise LangGraph passent par la gateway vers underwriting-admin, seul propriétaire de la base (D22 sans exception, D105 remplace D26).

**Architecture :** underwriting-admin stocke des points de reprise **opaques** (octets sérialisés par LangGraph, base64 en JSON) dans un contexte EF dédié ; la gateway relaie `/api/points-de-reprise/**` au seul cluster (rôle `PointsDeReprise` + `azp` du cluster) ; le cluster remplace `AsyncPostgresSaver` par un adapter `CheckpointerHttp` (`BaseCheckpointSaver`) qui appelle la gateway avec son jeton d'application, comme son export de traces.

**Tech Stack :** Python 3.12, LangGraph 1.2.16 / `langgraph-checkpoint` 4.3.0, httpx, azure-identity ; .NET 10, EF Core (Npgsql), YARP ; pytest, xUnit v3, WireMock.Net.

**Spec :** `docs/superpowers/specs/2026-10-28-o8-suppression-d26-design.md` (issue #154). Branche `feat/d105-points-de-reprise` depuis `main`.

## Global Constraints

- Aucune montée de version ; seule dépendance retirée : `langgraph-checkpoint-postgres` (et `psycopg[binary]` si plus utilisé par le cluster).
- Hexagonal côté cluster (adapter dans `infrastructure/langgraph/`) ; underwriting-admin sans couche Application artificielle (Api → Infrastructure), stockage opaque : **aucune interprétation** de l'état du graphe.
- `thread_id = numero_contrat` (existant). Le corps HTTP n'est jamais tracé ; les spans portent le gabarit de route.
- Pas de repli silencieux vers `MemorySaver` en Azure : si `APP_ENV` vaut `staging` ou `production` et que la configuration HTTP manque, le démarrage échoue. `MemorySaver` reste pour les tests et le local sans configuration.
- Pas de cache côté cluster ; aucun seuil de latence inventé (la porte des evals p95 ≤ 30 s reste la référence).
- Écritures Entra et Azure (`make entra`, `make annexe`) **à la main par Acerola**, avant la fusion ; jamais par un agent ni la CI.
- Gel des fusions sur `main` du 29/10 au matin à la fin de la démo du 30/10 : cette PR se fusionne **après**.
- Français partout ; TU / TI selon `.claude/rules/testing-pyramid.md`.

## Décisions du plan (constructeur, spec §8)

| Sujet | Décision |
|---|---|
| Routes (underwriting-admin, relayées telles quelles par la gateway) | `GET /api/points-de-reprise/{thread_id}?ns=&id=` (dernier point si `id` absent, 404 sinon) · `GET /api/points-de-reprise/{thread_id}/liste?ns=&avant=&limite=` (ordre `checkpoint_id` décroissant) · `PUT /api/points-de-reprise/{thread_id}` (un point) · `PUT /api/points-de-reprise/{thread_id}/ecritures` (écritures en attente d'une tâche) · `DELETE /api/points-de-reprise/{thread_id}` (tout le fil). Réponses 200/204, 404, 401/403 en ProblemDetails avec `code`. |
| Concurrence (R17) | Même sémantique qu'`AsyncPostgresSaver` : point = upsert sur (`thread_id`, `checkpoint_ns`, `checkpoint_id`) ; écriture = upsert si `idx < 0` (écritures spéciales `WRITES_IDX_MAP`), sinon ignorée si elle existe. Dernier écrit gagnant, jamais de 409. |
| Stockage | Base `dossiers`, schéma `points_reprise`, compte PostgreSQL `points_reprise` (remplace `agent_state`, variable `PG_POINTS_REPRISE_PASSWORD`, secret `pg-points-reprise-password`) ; tables créées par la migration EF avec le compte `migrateur`. |
| Rôle Entra | `PointsDeReprise` sur `agentinsurflow-underwriting`, id `7a1d9e40-2c3b-4f58-8a6e-1b9c0d2e3f04` (…f01 à …f03 sont pris : `UW_GESTIONNAIRE`, `UW_TELEMETRIE`, `UW_SCOPE` ; …f04 vérifié libre le 28/10), attribué au seul principal de service du cluster. |
| Suppression d'un fil | `adelete_thread` → `DELETE` ; le cluster n'en appelle pas d'autre (aucun usage actuel, la base reste éphémère). |
| Taille | Mesurée à la Task 5 sur un point réel ; un appel par point tant qu'elle reste sous la limite Kestrel par défaut (30 Mo) ; sinon, ruling consigné. |

## Review Focus

1. Gestionnaire, MCP ou rag qui appellent `/api/points-de-reprise/**` avec un jeton valide → 403 à la gateway **et** à underwriting-admin → tests `Points_de_reprise_refuses_sans_role` (UW) et `Points_de_reprise_refuses_a_un_autre_azp` (gateway).
2. Reprise après `interrupt()` : le graphe reprend à l'étape suivante avec le saver HTTP → test `test_reprise_apres_interrupt_par_http` (cluster, faux underwriting-admin).
3. `checkpoint_ns` vide (cas nominal) et `checkpoint_id` absent (dernier point) → tests `Lecture_du_dernier_point_sans_id` (UW) et `test_aget_tuple_sans_id_rend_le_dernier`.
4. Underwriting-admin ou gateway injoignable en Azure → l'évaluation échoue visiblement (erreur, pas `MemorySaver`) → test `test_azure_sans_configuration_http_refuse_de_demarrer`.
5. Numéro de contrat dans le chemin → masqué dans les spans de la gateway et d'underwriting-admin (processeur `MasquageNumero` existant) → test `Span_points_de_reprise_sans_numero` (UW).

---

### Task 1 : underwriting-admin — stockage des points de reprise (EF, migration, dépôt)

**Files :**
- Create : `underwriting-admin/src/AgentInsurFlow.UnderwritingAdmin.Infrastructure/PointsDeReprise/{PointsDeRepriseDbContext.cs, PointsDeRepriseDbContextFactory.cs, ConnexionsPointsDeReprise.cs, MigrationsPointsDeReprise.cs, DepotPointsDeRepriseEf.cs, PointsDeRepriseServices.cs, Migrations/…}` (calqués sur `Infrastructure/Traces/`)
- Create : `underwriting-admin/tests/AgentInsurFlow.UnderwritingAdmin.Infrastructure.Tests/PointsDeReprisePostgresTests.cs`
- Modify : `infra/postgres/init.sh` (compte `points_reprise` à la place d'`agent_state`, schéma `points_reprise` dans les bases `dossiers*`, droits SELECT/INSERT/UPDATE/DELETE sur les tables du schéma, accordés par défaut au compte), `docker-compose.yml` et `.env.example` (`PG_POINTS_REPRISE_PASSWORD` remplace `PG_AGENT_STATE_PASSWORD`).

**Interfaces :**
- Produces : `IDepotPointsDeReprise` (dans Infrastructure, port de stockage opaque) :
  - `Task<PointDeReprise?> LireAsync(string threadId, string ns, string? checkpointId, CancellationToken ct)` — avec ses écritures en attente triées par (`task_id`, `idx`) ;
  - `Task<IReadOnlyList<PointDeReprise>> ListerAsync(string threadId, string? ns, string? avant, int? limite, CancellationToken ct)` — `checkpoint_id` décroissant ;
  - `Task EcrireAsync(PointDeReprise point, CancellationToken ct)` ; `Task EcrireEcrituresAsync(string threadId, string ns, string checkpointId, string taskId, string taskPath, IReadOnlyList<EcritureEnAttente> ecritures, CancellationToken ct)` ; `Task SupprimerFilAsync(string threadId, CancellationToken ct)`.
  - `record PointDeReprise(string ThreadId, string Ns, string CheckpointId, string? ParentId, string Type, byte[] Checkpoint, string TypeMetadata, byte[] Metadata, IReadOnlyList<EcritureEnAttente> Ecritures)` ; `record EcritureEnAttente(string TaskId, int Idx, string Canal, string Type, byte[] Valeur, string TaskPath)`.

- [ ] **Step 1 : TI (PostgreSQL du compose, base `dossiers_test`), rouges.** `Lecture_apres_ecriture_rend_les_memes_octets`, `Lecture_du_dernier_point_sans_id`, `Liste_decroissante_avec_avant_et_limite`, `Ecriture_speciale_idx_negatif_remplace`, `Ecriture_normale_existante_ignoree`, `Suppression_du_fil_retire_points_et_ecritures`, `Compte_points_reprise_ne_lit_pas_les_dossiers` (le compte n'a aucun droit hors de son schéma).
- [ ] **Step 2 : constater l'échec** (`make -C underwriting-admin test` avec le compose).
- [ ] **Step 3 : contexte, migration `PointsDeReprise` (`dotnet ef migrations add`), dépôt** ; upserts en SQL paramétré (`ON CONFLICT … DO UPDATE` / `DO NOTHING`) comme `DepotTracesEf`.
- [ ] **Step 4 : succès**, puis `make -C underwriting-admin lint`.
- [ ] **Step 5 : commit** `feat(underwriting): stockage opaque des points de reprise (D105, S4)`.

### Task 2 : underwriting-admin — API des points de reprise

**Files :**
- Create : `underwriting-admin/src/AgentInsurFlow.UnderwritingAdmin.Api/PointsDeRepriseEndpoints.cs`
- Modify : `underwriting-admin/src/AgentInsurFlow.UnderwritingAdmin.Api/Program.cs` (politique `PointsDeReprise` = `RequireRole("PointsDeReprise")`, connexions et migrations au démarrage comme `Traces`, `MapPointsDeReprise()`)
- Create : `underwriting-admin/tests/AgentInsurFlow.UnderwritingAdmin.Api.Tests/PointsDeRepriseTests.cs` (dépôt simulé, `JetonsDeTest`)

**Interfaces :**
- Consumes : `IDepotPointsDeReprise` (Task 1).
- Produces : contrat HTTP (JSON snake_case) — corps du `PUT` point : `{ "ns", "checkpoint_id", "parent_id", "type", "checkpoint", "type_metadata", "metadata" }` (octets en base64) ; corps du `PUT ecritures` : `{ "ns", "checkpoint_id", "task_id", "task_path", "ecritures": [{ "idx", "canal", "type", "valeur" }] }` ; réponse `GET` : le point avec `"ecritures": [{ "task_id", "idx", "canal", "type", "valeur", "task_path" }]` ; `liste` : `{ "points": [...] }`.

- [ ] **Step 1 : TI rouges** : `Aller_retour_point_et_ecritures`, `Lecture_du_dernier_point_sans_id`, `Point_absent_404_avec_code` (`POINT_DE_REPRISE_INTROUVABLE`), `Points_de_reprise_refuses_sans_role` (jeton `Gestionnaire` ou `Telemetrie` → 403 `ACCES_REFUSE` sur les 5 routes), `Sans_jeton_401`, `Span_points_de_reprise_sans_numero` (chemin `AIF-2026-000001` → aucun `AIF-` dans les spans, gabarit de route en nom), `Corps_jamais_dans_un_span`.
- [ ] **Step 2 : constater l'échec.**
- [ ] **Step 3 : endpoints** (groupe `/api/points-de-reprise`, `RequireAuthorization("PointsDeReprise")`, tag OpenAPI `PointsDeReprise`).
- [ ] **Step 4 : succès**, `make -C underwriting-admin test` et `lint`.
- [ ] **Step 5 : commit** `feat(underwriting): API des points de reprise réservée au cluster (D105, S4)`.

### Task 3 : gateway — route réservée au cluster

**Files :**
- Modify : `gateway/src/AgentInsurFlow.Gateway.Api/appsettings.Routes.json` (route `underwriting-points-de-reprise`, `Match.Path` `/api/points-de-reprise/{**reste}`, cluster `underwriting`, `AuthorizationPolicy` `underwriting-points-de-reprise`, `X-Forwarded` `Set`)
- Modify : `gateway/src/AgentInsurFlow.Gateway.Api/Program.cs` (politique `underwriting-points-de-reprise` = rôle `PointsDeReprise` + `aud` underwriting + `azp` == `Entra:ClusterClientId`, route fermée si vide — modèle `underwriting-etat-mcp`)
- Modify : `infra/containerapp.yaml` (`Entra__ClusterClientId` = `${INSURFLOW_CLUSTER_CLIENT_ID}`)
- Test : `gateway/tests/AgentInsurFlow.Gateway.Api.Tests/` (WireMock, nouveau fichier `PointsDeRepriseTests.cs`)

- [ ] **Step 1 : TI rouges** : `Cluster_relaye_vers_underwriting` (jeton rôle + azp du cluster → requête reçue par WireMock, chemin et corps intacts), `Points_de_reprise_refuses_a_un_autre_azp` (même rôle, autre `azp` → 403), `Gestionnaire_refuse` (403), `Sans_client_cluster_configure_route_fermee` (403).
- [ ] **Step 2 : constater l'échec.** **Step 3 : implémenter.** **Step 4 : `make gateway-test`, `make -C gateway lint`.**
- [ ] **Step 5 : commit** `feat(gateway): points de reprise relayés au seul cluster (D105, S4)`.

### Task 4 : cluster — `CheckpointerHttp`

**Files :**
- Create : `agentic-cluster/agentinsurflow_cluster/infrastructure/langgraph/checkpoint_http.py`
- Modify : `agentic-cluster/agentinsurflow_cluster/infrastructure/langgraph/checkpoint.py` (`checkpointer()` : `CheckpointerHttp` si `GATEWAY_URL`, `UNDERWRITING_API_CLIENT_ID` (audience `api://<id>`), tenant et client du cluster sont posés ; sinon `MemorySaver` hors Azure, **erreur** si `APP_ENV` ∈ {staging, production})
- Modify : `agentic-cluster/pyproject.toml` (retrait `langgraph-checkpoint-postgres`, `psycopg[binary]` si plus importé), lock
- Delete : `agentic-cluster/tests/integration/test_checkpoint_postgres.py`
- Create : `agentic-cluster/tests/unit/test_checkpoint_http.py` (faux underwriting-admin en `httpx.MockTransport` : TU selon la pyramide), `agentic-cluster/tests/integration/test_checkpoint_http_compose.py` (vrai underwriting-admin du compose, sauté s'il est absent)

**Interfaces :**
- Consumes : contrat HTTP de la Task 2 ; `credential_application(tenant, client_id, assertion)` et `source_assertion(cfg)` (`infrastructure/entra/jetons.py`), comme `creer_exportateur()` de `infrastructure/otel/telemetrie.py`.
- Produces : `class CheckpointerHttp(BaseCheckpointSaver[str])` — `__init__(self, client: httpx.AsyncClient, jeton: Callable[[], str])` ; implémente `aget_tuple`, `alist`, `aput`, `aput_writes`, `adelete_thread` (+ les versions synchrones lèvent `NotImplementedError`, le cluster est asynchrone) ; sérialise par `self.serde.dumps_typed` / `loads_typed` ; `get_next_version` hérité.

- [ ] **Step 1 : TU rouges** : `test_aput_puis_aget_tuple_rend_le_meme_point`, `test_aget_tuple_sans_id_rend_le_dernier`, `test_aget_tuple_absent_rend_none` (404), `test_alist_ordre_avant_limite_et_filtre_metadata` (filtre appliqué côté client sur les métadonnées décodées), `test_aput_writes_puis_ecritures_en_attente_triees`, `test_adelete_thread`, `test_reprise_apres_interrupt_par_http` (graphe réel de `graphe.py` : pause puis reprise à l'étape suivante), `test_jeton_pose_en_bearer`, `test_erreur_http_remonte` (500 ou injoignable → exception, pas de point vide), `test_azure_sans_configuration_http_refuse_de_demarrer`, `test_hors_azure_sans_configuration_memory_saver`.
- [ ] **Step 2 : constater l'échec.**
- [ ] **Step 3 : implémenter** ; retirer l'import PostgreSQL et la dépendance ; `uv lock` sans montée de version des autres paquets.
- [ ] **Step 4 : `make test`, `make lint`** ; TI compose (`make test-integration`) avec `make up`.
- [ ] **Step 5 : commit** `feat(cluster): points de reprise par la gateway, plus d'accès PostgreSQL (D105, S4)`.

### Task 5 : retraits d'infrastructure, ordre de déploiement et preuve locale

**Files :**
- Modify : `infra/entra.sh` (`UW_POINTS_DE_REPRISE`, rôle ajouté à l'inscription d'underwriting, `attribuer "$uw" "$UW_POINTS_DE_REPRISE" <sp du cluster> "cluster → PointsDeReprise (underwriting)"`)
- Modify : `infra/postgres-annexe.sh` (secret `pg-points-reprise-password` sur la base et underwriting-admin ; plus de `checkpoint-dsn` sur le cluster), `infra/containerapp-postgres.yaml`, `infra/containerapp-underwriting.yaml` (`PG_POINTS_REPRISE_PASSWORD`), `infra/containerapp-cluster.yaml` (retrait `INSURFLOW_CHECKPOINT_DSN` ; `UNDERWRITING_API_CLIENT_ID` déjà présent), `infra/bootstrap.sh` (commentaire)
- Modify : `.github/workflows/deploy.yml` (retrait de la vérification `checkpoint-dsn` ; vérification `pg-points-reprise-password` sur underwriting-admin ; tag de l'image PostgreSQL annexe relevé si `init.sh` change son contenu — vérifier où il est construit et suivre la convention existante)
- Create : `tests/unit/test_d26_retire.py`

- [ ] **Step 1 : TU rouge** `test_plus_aucune_reference_d26` : aucune occurrence de `INSURFLOW_CHECKPOINT_DSN`, `checkpoint-dsn`, `agent_state`, `PG_AGENT_STATE_PASSWORD`, `langgraph-checkpoint-postgres` hors `docs/` et hors ce test ; `test_role_points_de_reprise_attribue_au_seul_cluster` (dans `entra.sh`, une seule ligne `attribuer … UW_POINTS_DE_REPRISE`, vers le cluster).
- [ ] **Step 2 : constater l'échec.**
- [ ] **Step 3 : retraits et ajouts.** Ordre de déploiement : vérifier si la gateway peut passer avant le cluster dans `deploy.yml` (elle lit le FQDN du cluster, stable d'une révision à l'autre) ; si oui, l'avancer ; sinon, laisser et consigner pourquoi dans le commit.
- [ ] **Step 4 : `make test`, `make lint`, `make up`** : une évaluation avec pause puis reprise fonctionne en local ; mesurer la taille d'un point de reprise réel (requête SQL sur `points_reprise`) et le nombre d'allers-retours par évaluation (spans de dépendance) ; consigner les deux chiffres dans le message de commit.
- [ ] **Step 5 : commit** `chore(infra): D26 retirée — compte agent_state, secret checkpoint-dsn, rôle PointsDeReprise (S4)`.

### Task 6 : documentation et dossier

**Files :**
- Create : `docs/dossier/amendements-d105.md` (section · texte actuel · texte corrigé, pour §4.6, L6 (règle D22 et schéma), L6.7, tableau « Schéma agent_state », Q8, addendum ; décision D105 qui remplace D26 et amende D10, D93, D100)
- Modify : `agentic-cluster/README.md`, `underwriting-admin/README.md`, `docs/rollback.md` (points de reprise dans `points_reprise` d'underwriting-admin, toujours perdus au déploiement), `docs/contrat-personnel.md` (K11 : à rejouer en staging après fusion)
- Create : `eval/preuves/recette-k11-AAAA-MM-JJ-staging.md` (gabarit vide : commande, résultat, allers-retours, p95 ajouté — rempli à la Task 7)

- [ ] **Step 1 : écrire** ; chaque texte « actuel » cité est recopié du dossier ou du dépôt, jamais reformulé de mémoire ; ce qui ne peut pas être vérifié porte « à vérifier dans le PDF ».
- [ ] **Step 2 : `make test`, `make lint`.**
- [ ] **Step 3 : commit** `docs(d105): amendements du dossier, README, rollback et contrat (S4)`.

### Task 7 : manuel (Acerola) — avant et après la fusion

- [ ] Avant la fusion (après la démo du 30/10) : ajouter `PG_POINTS_REPRISE_PASSWORD` au `.env` ; `make entra` (rôle `PointsDeReprise`) ; `make annexe` (staging puis production).
- [ ] Fusion de la PR ; staging déployé, E2E vert.
- [ ] K11 en staging : `make recette ACTION=redemarrer`, le dossier en pause reprend ; remplir `eval/preuves/recette-k11-…-staging.md` (allers-retours et p95 ajouté, depuis App Insights) ; porte des evals verte.
- [ ] Reporter `docs/dossier/amendements-d105.md` dans `dossier-conception-v1.2.pdf`.
