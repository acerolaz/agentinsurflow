# underwriting-admin — AgentInsurFlow

Service C# (.NET 10, Clean Architecture) : dossiers de souscription et référentiel SQL des traces. Port **8002**, joint par la gateway (`/api/contrats`, `/api/traces`, `/v1/traces`).

| Projet | Rôle |
|---|---|
| `Domain` | Cœur métier, aucune dépendance NuGet |
| `Application` | Cas d'usage (dépend de `Domain`) |
| `Infrastructure` | Adapters (dépend de `Application`, `Domain`) |
| `Api` | ASP.NET : `Program.cs`, jeton Entra (`AzureAd:*`), politiques `Gestionnaire` / `Telemetrie`, OpenAPI, OpenTelemetry |

- Refus par défaut : tout exige un jeton valide ; `GET /health` (`statut`, `version`, `release`) et `GET /openapi/v1.json` sont publics.
- JSON en snake_case ; erreurs en ProblemDetails avec `code` (`NON_AUTHENTIFIE`, `ACCES_REFUSE`).
- OpenAPI sans `servers` ; pas de Swagger UI propre : la page unique est celle de la gateway.

```bash
make lint test      # format + analyseurs ; TU + TI, couverture >= 80 %
make docker-build   # image locale
```

SDK .NET 10 requis (`global.json` à la racine du monorepo).
