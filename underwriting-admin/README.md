# underwriting-admin — AgentInsurFlow

Service C# (.NET 10, Clean Architecture), port **8002**, **sa propre Container App** (entrée interne, #70), jointe uniquement par la gateway, y compris par `rag`
(jeton On-Behalf-Of de l'utilisateur, D22). Seuls ses propres spans OTLP arrivent sur la boucle locale ; ceux de la gateway, de rag et du MCP arrivent avec un jeton d'application (rôle `Telemetrie`), `/v1/traces` refusant toute autre source non locale. Deux responsabilités :

- **Dossiers** : base `dossiers` (MCD Merise, migrations EF Core), lue par la **vue minimisée** avec le compte
  `dossiers` ; contrôle **BOLA** (`gestionnaire_id` = `oid` du jeton). Seules exceptions (décision d'Acerola, 27/10) :
  le contrat imprimé (`vue_contrat_accepte`, `vue_garanties_contrat_accepte`) et la fiche du lead
  (`vue_fiche_souscripteur`), jamais envoyés au cluster ni à un LLM (voir [`CLAUDE.md`](CLAUDE.md)).
- **Référentiel SQL des traces OpenTelemetry** : base `traces`, table `span` au modèle OTLP ; récepteur
  OTLP/HTTP protobuf.

| Route | Rôle | Réponses |
|---|---|---|
| `GET /api/contrats?limit&offset` | `Gestionnaire` | 200 (portefeuille du gestionnaire, `limit` ≤ 100) · 401 · 403 |
| `GET /api/contrats/{numero_contrat}` | `Gestionnaire` | 200 (vue minimisée, 10 champs en snake_case) · 404 `CONTRAT_INTROUVABLE` (inexistant **ou** à un autre gestionnaire) |
| `GET /api/contrats/{numero_contrat}/pieces` | `Gestionnaire` | 200 (pièces déclarées : type et date d'émission seulement) · 404 |
| `GET /api/contrats/{numero_contrat}/etat` | `Gestionnaire` | 200 (tentative courante : rapports des agents, sections lisibles, relances) · 404 |
| `GET /api/contrats/{numero_contrat}/contrat` | `Gestionnaire` | 200 (contrat imprimé : décision, prime, souscripteur avec coordonnées, véhicule, garanties ; `vue_contrat_accepte`) · 404 · 409 `CONTRAT_NON_ACCEPTE` |
| `GET /api/contrats/{numero_contrat}/souscripteur` | `Gestionnaire` | 200 (fiche du lead : civilité, identité, adresse, mobile, e-mail, véhicule ; `vue_fiche_souscripteur`) · 404 |
| `PUT /api/contrats/{numero_contrat}/brouillon` · `/statut` · `/observations` · `/etat` | `Gestionnaire` (écritures du cluster en OBO) | 204 · 400 (écriture refusée, avec `code`) · 404 · 409 `STATUT_FIGE` |
| `POST /api/contrats/{numero_contrat}/relances` | `Gestionnaire` | 201 (relance n/3) · 400 · 404 · 409 `RELANCES_EPUISEES`, `DOSSIER_DECIDE`, `RELANCE_CONCURRENTE` |
| `POST /api/contrats/{numero_contrat}/sans-suite` | `Gestionnaire` | 204 (`SANS_SUITE`, après la 3e relance et avant toute décision, K8) · 404 · 409 `DOSSIER_DECIDE`, `RELANCES_NON_EPUISEES` |
| `POST /v1/traces` | sans jeton depuis `Otlp:SourcesSansJeton` sans `X-Forwarded-For`, sinon `Telemetrie` | 200 (protobuf) · 400 `OTLP_INVALIDE` (protobuf illisible, identifiant de mauvaise longueur, horodatage > `long.MaxValue`) · 401 · 403 · 415 |
| `GET /api/traces/{trace_id}` | `Gestionnaire` | 200 (spans dans l'ordre) · 400 `TRACE_ID_INVALIDE` · 404 `TRACE_INTROUVABLE` |
| `GET /api/points-de-reprise/{thread_id}?ns&id` · `GET …/{thread_id}/liste?ns&avant&limite` | `PointsDeReprise` (cluster seul) | 200 (dernier point si `id` absent) · 404 · 401 · 403 |
| `PUT /api/points-de-reprise/{thread_id}` · `PUT …/{thread_id}/ecritures` · `DELETE …/{thread_id}` | `PointsDeReprise` (cluster seul) | 204 · 400 · 401 · 403 |
| `GET /health` | aucun | `statut`, `version` (SHA), `release` |
| `GET /openapi/v1.json` | aucun | Document affiché dans la page Swagger unique de la gateway (pas de Swagger UI propre) |

| Projet | Rôle |
|---|---|
| `Domain` | `VueContrat`, `Span`, règles pures (`TrancheAge`, `Departement`, `ReglesTraces`) — aucune dépendance NuGet |
| `Application` | Ports `IDepotDossiers`, `IDepotTraces` ; cas d'usage `ListerPortefeuille`, `ConsulterContrat`, `EnregistrerSpans`, `LireTrace` |
| `Infrastructure` | EF Core + Npgsql : `Dossiers/` (MCD, vue, seed, migrations), `Traces/` (table `span`), `Otlp/` (protobuf → `Span`) |
| `Api` | `Program.cs` : jeton Entra (`Microsoft.Identity.Web`, audiences `Entra:Audiences:underwriting`), politiques, routes, OpenTelemetry |

## Configuration

| Clé | Rôle |
|---|---|
| `AzureAd__TenantId`, `AzureAd__ClientId` | Inscription Entra `agentinsurflow-underwriting` |
| `Entra__Audiences__underwriting__0` | Liste « a, b » des audiences acceptées (la même que la gateway) |
| `PG_HOST`, `PG_PORT`, `PG_*_PASSWORD` | Comptes `migrateur`, `dossiers`, `traces_writer`, `traces_reader`, `points_reprise` (schéma `points_reprise`, mot de passe `PG_POINTS_REPRISE_PASSWORD`, secret `pg-points-reprise-password` ; tables créées par la migration EF avec `migrateur`, stockage opaque des points de reprise du cluster, D105). Hors Development, un mot de passe absent ou un `PG_PORT` invalide arrête le démarrage en nommant la clé |
| `Migrations__AuDemarrage` | `true` : migrations et seed au démarrage (compte `migrateur`, attente de PostgreSQL ≤ 60 s) |
| `SEED_GESTIONNAIRE_A`, `SEED_GESTIONNAIRE_B`, `SEED_GESTIONNAIRE_C` | `oid` Entra des gestionnaires du seed (jamais commités) : `AIF-2026-000001` à `000003` et `000010` (refusé par le barème, R01) → A, `000004` à `000006` → B (A et B : comptes humains de la démo), `000007` à `000009` → C (identité de la CI, migration `SeedGestionnaireC`, facultative). Une valeur qui n'est pas un GUID fait échouer la migration du seed |
| `Otlp__SourcesSansJeton` | CIDR acceptés sans jeton sur `/v1/traces` (défaut : boucle locale) ; un CIDR invalide fait échouer la première requête avec une erreur qui nomme la clé et la valeur |

## Commandes

```bash
make lint test         # format + analyseurs ; TU + TI (PostgreSQL du compose), couverture ≥ 80 % (couverture.py)
make docker-build      # image locale
make -C .. openapi     # docs/openapi/underwriting-admin.json, généré au build
```

SDK .NET 10 requis (`global.json` à la racine du monorepo). Données : [`docs/donnees/modele.md`](../docs/donnees/modele.md),
[`docs/donnees/traces.md`](../docs/donnees/traces.md).
