# 🚪 Gateway — AgentInsurFlow

**Seule entrée publique** de la solution (décision S3-18) : un reverse proxy **YARP** sur ASP.NET Core 10 qui répartit les appels entre `rag` (Python) et `underwriting-admin` (C#). C'est la forme minimale de la gateway prévue par le dossier de conception (topologie en étoile D22, YARP D40).

> 🔁 **Analogie .NET** : c'est un `Ocelot`/`YARP` classique, avec ses routes déclarées dans `appsettings`, pas dans le code.

## Ce qu'elle fait — et ne fait pas

| ✅ Elle fait | ⛔ Elle ne fait pas |
|---|---|
| Router par préfixe de chemin (table ci-dessous) | Valider un jeton, lire un rôle, décider d'un accès |
| **Réécrire** `X-Forwarded-For`/`-Proto`/`-Host`/`-Prefix` (mode `Set`) : un client ne peut pas se faire passer pour un appel interne | Contenir une règle métier |
| Transmettre tels quels `Authorization` et `traceparent` | Modifier un corps de requête |
| Exposer sa santé (`/health`) et celle des services (`/health/rag`, `/health/underwriting`) | — |
| Émettre ses spans OpenTelemetry vers le référentiel SQL d'`underwriting-admin` | — |

Chaque service valide lui-même les jetons qu'il reçoit : la gateway n'a **aucune** logique d'autorisation (même règle que l'`api-gateway` de Sorabel).

## Routes

| Préfixe public | Service | Chemin reçu par le service |
|---|---|---|
| `/api/**` | `rag` | identique |
| `/v1/ingestion/**` | `rag` | identique |
| `/internal/rag/**` | `rag` | identique |
| `/rag/**` (Swagger, OpenAPI) | `rag` | sans le préfixe `/rag` |
| `/health/rag` | `rag` | `/health` |
| `/internal/sql/**` | `underwriting-admin` | identique |
| `/internal/traces/**` | `underwriting-admin` | identique |
| `/v1/traces` | `underwriting-admin` | identique |
| `/underwriting/**` (Swagger, OpenAPI) | `underwriting-admin` | sans le préfixe `/underwriting` |
| `/health/underwriting` | `underwriting-admin` | `/health` |
| `/health` | la gateway elle-même | — |
| tout autre chemin | — | **404**, aucun appel transmis |

Fichier : `src/AgentInsurFlow.Gateway.Api/appsettings.Routes.json`. Il est chargé **en premier** : toute variable d'environnement le surcharge.

## Configuration

| Variable | Défaut | Rôle |
|---|---|---|
| `ReverseProxy__Clusters__rag__Destinations__d1__Address` | `http://localhost:8001` | Adresse de `rag` (compose : `http://rag:8001`) |
| `ReverseProxy__Clusters__underwriting__Destinations__d1__Address` | `http://localhost:8002` | Adresse d'`underwriting-admin` |
| `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | `http://localhost:8002/v1/traces` | Récepteur OTLP des traces |
| `APP_VERSION`, `APP_RELEASE` | `dev` | Versions servies par `/health` (gravées au build) |
| `ASPNETCORE_HTTP_PORTS` | `8000` (image) | Port d'écoute |

## Commandes

Prérequis : **SDK .NET 10** (`global.json` à la racine du monorepo).

```bash
make -C gateway build          # compilation (avertissements = erreurs)
make -C gateway lint           # dotnet format --verify-no-changes
make -C gateway test           # tests + couverture de lignes >= 80 %
make -C gateway docker-build   # image (contexte = racine du monorepo)
docker run --rm -p 8000:8000 agentinsurflow-gateway:local
curl localhost:8000/health
```

## Tests — forme « diamant »

Un proxy pur n'a presque aucune logique isolable : ses tests sont des **tests d'intégration** (`WebApplicationFactory` devant deux backends **WireMock.Net**), pas des tests unitaires de configuration. C'est l'exception prévue par la pyramide de la solution (70 % TU / 20 % TI / 10 % E2E sur `rag` et `underwriting-admin`) ; les tests de la gateway sont comptés à part.

| Test | Ce qu'il prouve |
|---|---|
| `Route_vers_le_bon_backend` (8 cas) | Chaque préfixe atteint le bon service, avec le bon chemin, et pas l'autre |
| `Chemin_inconnu_404_sans_appel_backend` | Aucune route fourre-tout |
| `Transmet_XForwardedFor_reecrit` | Un `X-Forwarded-For` fourni par le client n'arrive pas au service (règle S3-21) |
| `Transmet_Authorization_et_traceparent_sans_les_lire` | Jeton et contexte de trace transmis intacts |
| `Ne_controle_aucun_jeton` | Sans jeton, la requête passe : le service décide |
| `Health_repond_sans_backend`, `Health_des_services_route_vers_leur_health` | Santé de la gateway et des services |

## Architecture

Clean Architecture **sans couche artificielle** (`~/.claude/rules/csharp-clean-architecture.md`) : un proxy pur n'a ni domaine ni cas d'usage, donc un seul projet `Api` (`Program.cs` + routes déclaratives) et un projet de tests sous `tests/`, rattaché au dossier de solution `/tests/` du `.slnx`.

```
gateway/
├── AgentInsurFlow.Gateway.slnx
├── src/AgentInsurFlow.Gateway.Api/      Program.cs · appsettings.json · appsettings.Routes.json
├── tests/AgentInsurFlow.Gateway.Api.Tests/
├── Dockerfile · Makefile · README.md
```

## Déploiement

La gateway sera le conteneur exposé (port 8000) de la Container App à 4 conteneurs (Task U5 du plan). D'ici là, elle est construite et testée par la CI (job `gateway`) mais **pas encore déployée** : le déploiement actuel de `rag` est inchangé.
