# underwriting-admin — AgentInsurFlow

Service C# (.NET 10, Clean Architecture), port **8002**, joint uniquement par la gateway, y compris par `rag`
(jeton On-Behalf-Of de l'utilisateur, D22) ; seuls les spans OTLP arrivent sur la boucle locale. Deux responsabilités :

- **Dossiers** : base `dossiers` (MCD Merise, migrations EF Core), lue par la **vue minimisée** avec le compte
  `dossiers` ; contrôle **BOLA** (`gestionnaire_id` = `oid` du jeton).
- **Référentiel SQL des traces OpenTelemetry** : base `traces`, table `span` au modèle OTLP ; récepteur
  OTLP/HTTP protobuf.

| Route | Rôle | Réponses |
|---|---|---|
| `GET /api/contrats?limit&offset` | `Gestionnaire` | 200 (portefeuille du gestionnaire, `limit` ≤ 100) · 401 · 403 |
| `GET /api/contrats/{numero_contrat}` | `Gestionnaire` | 200 (vue minimisée, 10 champs en snake_case) · 404 `CONTRAT_INTROUVABLE` (inexistant **ou** à un autre gestionnaire) |
| `POST /v1/traces` | sans jeton depuis `Otlp:SourcesSansJeton` sans `X-Forwarded-For`, sinon `Telemetrie` | 200 (protobuf) · 400 `OTLP_INVALIDE` (protobuf illisible, identifiant de mauvaise longueur, horodatage > `long.MaxValue`) · 401 · 403 · 415 |
| `GET /api/traces/{trace_id}` | `Gestionnaire` | 200 (spans dans l'ordre) · 400 `TRACE_ID_INVALIDE` · 404 `TRACE_INTROUVABLE` |
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
| `PG_HOST`, `PG_PORT`, `PG_*_PASSWORD` | Comptes `migrateur`, `dossiers`, `traces_writer`, `traces_reader`. Hors Development, un mot de passe absent ou un `PG_PORT` invalide arrête le démarrage en nommant la clé |
| `Migrations__AuDemarrage` | `true` : migrations et seed au démarrage (compte `migrateur`, attente de PostgreSQL ≤ 60 s) |
| `SEED_GESTIONNAIRE_A`, `SEED_GESTIONNAIRE_B` | `oid` Entra des deux gestionnaires du seed (jamais commités) : `AIF-2026-000001` à `000003` → A, `000004` à `000006` → B. Une valeur qui n'est pas un GUID fait échouer la migration du seed |
| `Otlp__SourcesSansJeton` | CIDR acceptés sans jeton sur `/v1/traces` (défaut : boucle locale) ; un CIDR invalide fait échouer la première requête avec une erreur qui nomme la clé et la valeur |

## Commandes

```bash
make lint test         # format + analyseurs ; TU + TI (PostgreSQL du compose), couverture ≥ 80 % (couverture.py)
make docker-build      # image locale
make -C .. openapi     # docs/openapi/underwriting-admin.json, généré au build
```

SDK .NET 10 requis (`global.json` à la racine du monorepo). Données : [`docs/donnees/modele.md`](../docs/donnees/modele.md),
[`docs/donnees/traces.md`](../docs/donnees/traces.md).
