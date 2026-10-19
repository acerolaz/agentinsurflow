# 🚪 Gateway — AgentInsurFlow

**Seule entrée publique** de la solution (décision S3-18) : un reverse proxy **YARP** sur ASP.NET Core 10 qui répartit les appels entre `rag` (Python) et `underwriting-admin` (C#), et qui sert la **page Swagger unique** des trois API. C'est la forme minimale de la gateway prévue par le dossier de conception (topologie en étoile D22, YARP D40).

> 🔁 **Analogie .NET** : un `YARP`/`Ocelot` classique, routes déclarées dans `appsettings`, pas dans le code.

## Ce qu'elle fait — et ne fait pas

| ✅ Elle fait | ⛔ Elle ne fait pas |
|---|---|
| Router **par ressource REST** (table ci-dessous) | Valider un jeton, lire un rôle, décider d'un accès |
| **Réécrire** `X-Forwarded-For`/`-Proto`/`-Host`/`-Prefix` (mode `Set`) : un client ne peut pas se faire passer pour un appel interne | Contenir une règle métier |
| Transmettre tels quels `Authorization` et `traceparent` | Modifier un corps de requête |
| Servir la **page Swagger** des 3 API, à la racine `/` | — |
| Exposer sa santé (`/health`) et celle des services (`/health/rag`, `/health/underwriting`) | — |
| Émettre ses spans OpenTelemetry vers le référentiel SQL d'`underwriting-admin` | — |

Chaque service valide lui-même les jetons qu'il reçoit : la gateway n'a **aucune** logique d'autorisation.

## Contrat REST (S3-24)

| Méthode · URI publique | Service | Succès | Ressource |
|---|---|---|---|
| `POST /api/reponses` | `rag` | 200 | Réponse citée de l'agent à une question (calculée, non conservée : RGPD) |
| `POST /api/ingestions` | `rag` | 201 + `Location` | Ingestion d'un lot d'articles |
| `GET /api/ingestions`, `GET /api/ingestions/{id}` | `rag` | 200 | Rapports d'ingestion journalisés |
| `GET /api/extraits?question=…&top_k=5` | `rag` | 200 | Extraits du corpus passant la porte de pertinence (`NOT_FOUND_IN_CORPUS` sinon) |
| `GET /api/documents/{doc_id}` | `rag` | 200 · 404 | Document source, ses versions et ses chunks (traçabilité) |
| `GET /api/contrats?limit&offset`, `GET /api/contrats/{numero_contrat}` | `underwriting-admin` | 200 · 404 | Portefeuille du gestionnaire, vue minimisée (BOLA : 404 hors portefeuille) |
| `GET /api/traces/{trace_id}` | `underwriting-admin` | 200 · 404 | Trace OpenTelemetry, tous services confondus |
| `POST /v1/traces` | `underwriting-admin` | 200 | **Exception** : chemin imposé par la norme OTLP (récepteur de spans), pas une API métier |
| `GET /health`, `/health/rag`, `/health/underwriting` | gateway, services | 200 | Santé et versions |

Règles communes : ressources au pluriel ; `GET` sans effet de bord ; `POST` pour créer ou calculer ; `201` + `Location` à la création ; erreurs au format **ProblemDetails** (RFC 9457) avec un champ `code` (`CONTRAT_INTROUVABLE`…) ; pagination `limit`/`offset`. Tout chemin non listé : **404**, sans appel transmis.

### Correspondance avec les noms du brief (livrable L9)

Le brief et le dossier de conception nomment les endpoints de données en style RPC. Ils sont remplacés par le contrat REST ci-dessus :

| Nom dans le brief / dossier | Endpoint REST |
|---|---|
| `POST /api/agent` (sprint 2) | `POST /api/reponses` |
| `/v1/ingestion` | `POST /api/ingestions` (+ `GET /api/ingestions[/{id}]`) |
| `/internal/rag/search` | `GET /api/extraits?question=…` |
| `/internal/rag/documents/{doc_id}` | `GET /api/documents/{doc_id}` |
| `/internal/sql/…` (contrats) | `GET /api/contrats[/{numero_contrat}]` |
| `/internal/traces/{trace_id}` | `GET /api/traces/{trace_id}` |

## Swagger

- **Une seule page**, à la racine de la gateway (`/` → `/index.html`), avec un menu qui donne accès aux **3 documents OpenAPI** : `rag` (`/rag/openapi.json`), `underwriting-admin` (`/underwriting/openapi/v1.json`) et la gateway (`/openapi/v1.json`).
- **Préfixe public transmis** : pour `/rag/**` et `/underwriting/**`, la gateway retire le préfixe et l'envoie dans `X-Forwarded-Prefix` ; chaque service l'utilise pour que ses liens Swagger restent justes derrière la gateway. Un `X-Forwarded-Prefix` fourni par le client est ignoré.
- **Connexion Entra** (« Authorize ») en code d'autorisation + **PKCE**, avec un seul client public : `SWAGGER_CLIENT_ID` (l'application `agentinsurflow-rag`, qui a déjà la permission vers `underwriting` pour l'On-Behalf-Of).

## Configuration

| Variable | Défaut | Rôle |
|---|---|---|
| `ReverseProxy__Clusters__rag__Destinations__d1__Address` | `http://localhost:8001` | Adresse de `rag` (compose : `http://rag:8001`) |
| `ReverseProxy__Clusters__underwriting__Destinations__d1__Address` | `http://localhost:8002` | Adresse d'`underwriting-admin` |
| `SWAGGER_CLIENT_ID` | vide | Client Entra public de la page Swagger |
| `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | `http://localhost:8002/v1/traces` | Récepteur OTLP des traces |
| `APP_VERSION`, `APP_RELEASE` | `dev` | Versions servies par `/health` (gravées au build) |
| `ASPNETCORE_HTTP_PORTS` | `8000` (image) | Port d'écoute |

Les routes (`src/AgentInsurFlow.Gateway.Api/appsettings.Routes.json`) sont chargées **en premier** : toute variable d'environnement les surcharge.

## Commandes

Prérequis : **SDK .NET 10** (`global.json` à la racine du monorepo).

```bash
make -C gateway build          # compilation (avertissements = erreurs)
make -C gateway lint           # dotnet format --verify-no-changes
make -C gateway test           # tests + couverture de lignes >= 80 %
make -C gateway docker-build   # image (contexte = racine du monorepo)
docker run --rm -p 8000:8000 agentinsurflow-gateway:local
open http://localhost:8000/    # page Swagger
```

## Tests — forme « diamant »

Un proxy pur n'a presque aucune logique isolable : ses tests sont des **tests d'intégration** (`WebApplicationFactory` devant deux backends **WireMock.Net**), pas des tests unitaires de configuration. C'est l'exception prévue par la pyramide de la solution (70 % TU / 20 % TI / 10 % E2E sur `rag` et `underwriting-admin`) ; les tests de la gateway sont comptés à part.

| Test | Ce qu'il prouve |
|---|---|
| `Route_vers_le_bon_backend` (11 cas) | Chaque ressource REST atteint le bon service, avec le bon chemin, et pas l'autre |
| `Chemin_non_route_404_sans_appel_backend` (6 cas) | Ni route fourre-tout, ni anciennes routes RPC (`/api/agent`, `/v1/ingestion`, `/internal/…`) |
| `Transmet_XForwardedFor_reecrit`, `XForwardedPrefix_du_client_ne_passe_pas` | Les en-têtes `X-Forwarded-*` du client n'atteignent pas les services (règle S3-21) |
| `Documentation_recoit_son_prefixe_public` | `/rag` et `/underwriting` transmis en `X-Forwarded-Prefix` |
| `Transmet_Authorization_et_traceparent_sans_les_lire`, `Ne_controle_aucun_jeton` | Jeton et contexte de trace intacts ; aucune décision d'accès |
| `Racine_redirige_vers_la_page_swagger`, `Page_swagger_liste_les_trois_documents`, `Page_swagger_se_connecte_a_Entra_en_PKCE` | La page Swagger unique et sa connexion |
| `OpenApi_de_la_gateway_documente_health`, `Health_*` | Document OpenAPI et santé |

## Architecture

Clean Architecture **sans couche artificielle** (`~/.claude/rules/csharp-clean-architecture.md`) : un proxy pur n'a ni domaine ni cas d'usage, donc un seul projet `Api` (`Program.cs` + routes déclaratives) et un projet de tests sous `tests/`, rattaché au dossier de solution `/tests/` du `.slnx`.

```
gateway/
├── AgentInsurFlow.Gateway.slnx
├── src/AgentInsurFlow.Gateway.Api/      Program.cs · appsettings.json · appsettings.Routes.json
├── tests/AgentInsurFlow.Gateway.Api.Tests/   RoutageTests.cs · SwaggerTests.cs
├── Dockerfile · Makefile · README.md
```

## Déploiement

La gateway sera le conteneur exposé (port 8000) de la Container App à 4 conteneurs (Task U5 du plan). D'ici là, elle est construite et testée par la CI (job `gateway`) mais **pas encore déployée** : le déploiement actuel de l'API Python est inchangé.
