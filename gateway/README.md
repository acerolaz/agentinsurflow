# 🚪 Gateway — AgentInsurFlow

**Seule entrée publique** de la solution (décision S3-18) : un reverse proxy **YARP** sur ASP.NET Core 10 qui répartit les appels entre `rag` (Python) et `underwriting-admin` (C#), et qui sert la **page Swagger unique** des trois API. C'est la forme minimale de la gateway prévue par le dossier de conception (topologie en étoile D22, YARP D40).

> 🔁 **Analogie .NET** : un `YARP`/`Ocelot` classique, routes **et politiques d'autorisation** déclarées dans `appsettings`, pas dans le code.

## Ce qu'elle fait — et ne fait pas

| ✅ Elle fait | ⛔ Elle ne fait pas |
|---|---|
| Router **par ressource REST** (table ci-dessous) | Remplacer la validation des services (BOLA, règles fines) |
| **Valider le jeton Entra et exiger un rôle par route** (S3-25, issue #9) | Avoir sa propre inscription d'application |
| **Limiter le débit** par utilisateur et application (`oid` + `azp`) ou par IP, 429 (S3-27, issue #13) | Partager ses compteurs entre répliques |
| **Réécrire** `X-Forwarded-For`/`-Proto`/`-Host`/`-Prefix` (mode `Set`) : un client ne peut pas se faire passer pour un appel interne | Contenir une règle métier |
| Transmettre tels quels `Authorization` et `traceparent` | Modifier un corps de requête |
| Servir la **page Swagger** des 3 API, à la racine `/` | — |
| Exposer sa santé (`/health`) et celle des services (`/health/rag`, `/health/underwriting`) | — |
| Émettre ses spans OpenTelemetry vers le référentiel SQL d'`underwriting-admin` | — |

La gateway est la **première barrière** ; chaque service revalide le jeton qu'il reçoit (défense en profondeur).

## Sécurité (S3-25)

Jeton **Entra ID** (Bearer) validé à l'entrée : signature (clés publiées par le tenant), émetteur v1 ou v2 du tenant, expiration, audience de l'un des deux services. Puis **une politique par route**, déclarée dans `appsettings.Routes.json` (`AuthorizationPolicy`) ; chaque politique exige un rôle d'app **et** l'audience du service visé : un jeton émis pour `rag` n'ouvre pas `underwriting-admin`.

| Route | Politique | Rôle d'app | Audience |
|---|---|---|---|
| `POST /api/reponses`, `GET /api/extraits`, `GET /api/documents/{doc_id}`, `GET /api/documents/{doc_id}/attribution` | `rag-gestionnaire` | `Gestionnaire` | `agentinsurflow-rag` |
| `POST`/`GET /api/ingestions[/{id}]` | `rag-ingestion` | `Ingestion` | `agentinsurflow-rag` |
| `GET /api/contrats[/{numero_contrat}]`, `GET /api/traces/{trace_id}` | `underwriting-gestionnaire` | `Gestionnaire` | `agentinsurflow-underwriting` |
| `POST /v1/traces` | `underwriting-telemetrie` | `Telemetrie` | `agentinsurflow-underwriting` |
| `/`, `/openapi/v1.json`, `GET /rag/openapi.json`, `GET /underwriting/openapi/v1.json`, `/health*` | `anonymous` | — | — |

Les routes de documentation n'ouvrent **que** le document OpenAPI de chaque service : tout autre chemin sous `/rag/` ou `/underwriting/` tombe dans le refus par défaut (sinon `/rag/api/reponses` atteindrait `rag` sans jeton ni limite de débit). Le « Try it out » de la page Swagger appelle les routes REST publiques (`/api/…`), donc avec leur politique.

- **Refus par défaut** : tout le reste exige au moins un jeton valide (un chemin inconnu répond 401 sans jeton, 404 avec).
- Erreurs en ProblemDetails : **401** `NON_AUTHENTIFIE` (+ `WWW-Authenticate: Bearer`), **403** `ACCES_REFUSE` ; aucun appel n'est transmis.
- Appelants : les humains (Swagger en PKCE, `az login`), la CI (identité fédérée OIDC de GitHub Actions). `rag` lit les dossiers d'`underwriting-admin` en On-Behalf-Of **par la gateway** (`/api/contrats`, politique `underwriting-gestionnaire`), comme tout appelant (D22). Seul l'export OTLP des spans reste sur la boucle locale (S3-21).
- Sans `Entra__TenantId` ou sans audiences, la gateway **refuse de démarrer** plutôt que de s'ouvrir.

## Limitation de débit (S3-27, issue #13)

Limiteur **natif** d'ASP.NET Core (aucun paquet), en fenêtre fixe de 60 s, par **utilisateur et application cliente** (`oid` + `azp` du jeton, `Partition` de `Program.cs` ; sans `azp`, l'`oid` seul), ou, sans jeton, par **IP**. Les agents du cluster appellent en OBO pour le même gestionnaire, chacun avec son `azp` : sans `azp` dans la clé, une évaluation épuiserait la fenêtre du gestionnaire. La limite `llm` fait exception : par application appelante seule (`azp`, repli `appid`). Budgets :

| Portée | Limite par défaut | Réglage |
|---|---|---|
| Toutes les routes | 120 requêtes/min | `RateLimit__Global__PermitLimit` |
| `POST /api/reponses` (coût LLM), en plus de la limite globale | 10 requêtes/min | `RateLimit__Reponses__PermitLimit` |
| `/v1/souscriptions/{numero_contrat}/evaluation` et `/revue` (cluster, plusieurs appels LLM par évaluation) | 10 requêtes/min (défaut du code) | `RateLimit__Cluster__PermitLimit` |
| `/health`, `/health/rag`, `/health/underwriting` (sondes) | jamais limitées | — |

Au-delà : **429** `TROP_DE_REQUETES` en ProblemDetails, avec `Retry-After` (secondes). Le débit est compté après l'authentification et avant l'autorisation : les requêtes refusées comptent aussi. Les compteurs sont en mémoire, par réplique (la Container App n'a qu'une réplique).

## IP réelle du client (S3-26, issue #10)

En Azure, la gateway est derrière l'**envoy** de Container Apps, qui ajoute l'IP du client à la fin de `X-Forwarded-For`. Avec `Proxy__EnvoyDevant=true`, la gateway reprend **cette dernière entrée seulement** (`ForwardedHeaders`, `ForwardLimit = 1`) : elle sert au débit par IP, aux spans (`client.address`) et à l'`X-Forwarded-For` transmis aux services. Le drapeau est **éteint par défaut** : en local, la gateway est joignable directement et cet en-tête viendrait du client lui-même ; il est alors ignoré.

## Contrat REST (S3-24)

| Méthode · URI publique | Service | Succès | Ressource |
|---|---|---|---|
| `POST /api/reponses` | `rag` | 200 | Réponse citée de l'agent à une question (calculée, non conservée : RGPD) |
| `POST /api/ingestions` | `rag` | 201 + `Location` | Ingestion d'un lot d'articles |
| `GET /api/ingestions`, `GET /api/ingestions/{id}` | `rag` | 200 | Rapports d'ingestion journalisés |
| `GET /api/extraits?question=…&top_k=5` | `rag` | 200 | Extraits du corpus passant la porte de pertinence (`NOT_FOUND_IN_CORPUS` sinon) |
| `GET /api/documents/{doc_id}` | `rag` | 200 · 404 | Document source, ses versions et ses chunks (traçabilité) |
| `GET /api/documents/{doc_id}/attribution?version=` | `rag` | 200 · 404 | Mentions Etalab 2.0 d'un article cité |
| `GET /api/contrats?limit&offset`, `GET /api/contrats/{numero_contrat}` | `underwriting-admin` | 200 · 404 | Portefeuille du gestionnaire, vue minimisée (BOLA : 404 hors portefeuille) |
| `GET /api/traces/{trace_id}` | `underwriting-admin` | 200 · 404 | Trace OpenTelemetry, tous services confondus |
| `POST /v1/traces` | `underwriting-admin` | 200 | **Exception** : chemin imposé par la norme OTLP (récepteur de spans), pas une API métier |
| `GET /health`, `/health/rag`, `/health/underwriting` | gateway, services | 200 | Santé et versions |

Règles communes : ressources au pluriel ; `GET` sans effet de bord ; `POST` pour créer ou calculer ; `201` + `Location` à la création ; erreurs au format **ProblemDetails** (RFC 9457) avec un champ `code` (`CONTRAT_INTROUVABLE`…) ; pagination `limit`/`offset`. Tout chemin non listé : **404** (401 sans jeton, refus par défaut), sans appel transmis.

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

## Exception JSON-RPC : `/mcp`

`/mcp` est la seule route qui n'est pas du REST : le serveur MCP (`serveur-mcp`, port 8003) parle MCP en Streamable HTTP (`POST` JSON-RPC, réponse JSON ou `text/event-stream`, `GET` pour ouvrir un flux SSE ; sans session côté serveur, `DELETE` n'est pas routé). Aucun document OpenAPI : les outils et leurs schémas sont renvoyés par `tools/list`.

- **Autorisation à deux niveaux** : la gateway exige un jeton d'audience `mcp` (`Entra__Audiences__mcp__0`, `api://agentinsurflow-mcp`) avec le rôle `Gestionnaire` ; le serveur MCP revalide le jeton, puis les services appelés revalident le leur.
- **Flux sans tampon** : YARP relaie les événements SSE au fil de l'eau (testé) ; `ActivityTimeout` de 5 min sur le cluster `mcp`. `traceparent` est relayé.
- **Débit** : `RateLimit__Mcp__PermitLimit` (60 requêtes/min par utilisateur et application), en plus de la limite globale.
- Outils, codes d'erreur : voir `serveur-mcp/README.md`.
- Les écritures `PUT /api/contrats/{numéro}/brouillon` et `/statut` passent par la route `underwriting-contrats` existante. `PUT /api/contrats/{numéro}/etat` (mémoire du dossier) a sa propre route `underwriting-etat`, déclarée avant : elle exige, en plus du rôle `Gestionnaire` et de l'audience underwriting, `azp` = `Entra:McpClientId` (`MCP_API_CLIENT_ID`, le client OBO du serveur MCP) ; un gestionnaire en direct reçoit `403`, et sans `Entra:McpClientId` la route est fermée.

## Routes du cluster d'agents

`POST /v1/souscriptions/{numero_contrat}/evaluation` est réécrite en `POST /evaluations/{numero_contrat}` et `POST /v1/souscriptions/{numero_contrat}/revue` en `POST /evaluations/{numero_contrat}/revue`, vers le cluster `cluster` (Container App interne ; compose : `http://agentic-cluster:8004`). Politique `cluster-gestionnaire` : rôle `Gestionnaire` **et** audience `Entra__Audiences__cluster__0` (`api://agentinsurflow-cluster`). Le jeton du gestionnaire est **relayé tel quel** (comme pour `/mcp`) : le cluster le revalide, puis l'échange en OBO. Débit : limite `cluster` (`RateLimit__Cluster__PermitLimit`, 10/min), par `oid` + `azp`. `GET /health/cluster` est anonyme ; le document OpenAPI du cluster est servi en `/cluster/openapi.json` (page Swagger unique). Voir [`agentic-cluster/README.md`](../agentic-cluster/README.md).

## Swagger

- **Une seule page**, à la racine de la gateway (`/` → `/index.html`), avec un menu qui donne accès aux **3 documents OpenAPI** : `rag` (`/rag/openapi.json`), `underwriting-admin` (`/underwriting/openapi/v1.json`) et la gateway (`/openapi/v1.json`).
- **Préfixe public transmis** : pour `GET /rag/openapi.json` et `GET /underwriting/openapi/v1.json`, la gateway retire le préfixe et l'envoie dans `X-Forwarded-Prefix`. Un `X-Forwarded-Prefix` fourni par le client est ignoré. Les documents des services ne déclarent **pas** de `servers` : le « Try it out » vise la gateway elle-même.
- **Connexion Entra** (« Authorize ») en code d'autorisation + **PKCE**, avec un seul client public : `SWAGGER_CLIENT_ID` (l'application `agentinsurflow-rag`, qui a déjà la permission vers `underwriting` pour l'On-Behalf-Of).

## Route `/api/llm/*` (Azure AI Foundry)

`POST /api/llm/{**reste}` est réécrit en `/openai/{**reste}` vers le cluster `llm` (`ReverseProxy__Clusters__llm__Destinations__d1__Address` = endpoint Foundry). Politique `llm-appelant` : rôle `LLM` **et** audience `Entra__Audiences__llm__0` (`api://…`, plus le GUID en `__1`). Même échange de jeton que `calcul` (table route → portée) : portée `Llm__Portee` (`https://cognitiveservices.azure.com/.default`), jeton de la gateway ; échec : `502` `LLM_INDISPONIBLE`. Credential : `ClientSecretCredential` si `Gateway__ClientSecret` est défini (local, avec `Gateway__ClientId`), sinon identité managée. Débit : limite `llm` (`RateLimit__Llm__PermitLimit`, 30/min) partitionnée par application appelante (`azp`, repli `appid`). Les réponses en flux ne sont pas tamponnées. Mesure (#70) : sur le span serveur de la requête, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.response.model` (réponse JSON, nombres et nom de modèle seulement, jamais de texte) et `appelant.azp` ; à lire dans le référentiel des traces d'underwriting-admin. Réponse en flux : `gen_ai.usage.mesure=non_disponible` (non mesuré, à revoir avec `stream_options.include_usage` au moment du budget).

## Route `/api/calcul/*` (Function de calcul)

`POST /api/calcul/{**reste}` est réécrit en `/api/{**reste}` vers le cluster `calcul` (ex. `/api/calcul/evaluer` donne `/api/evaluer`) ; la gateway **échange le jeton** : le jeton entrant (application du serveur MCP, rôle `Calcul` **et** audience `calcul`, politique `calcul-mcp`, `Entra__Audiences__calcul__0`) n'est jamais relayé ; elle le remplace par son propre jeton d'application, obtenu avec son identité managée pour la portée `Calcul__Portee` (`Authorization: Bearer <jeton de la gateway>`). Sans portée (local), aucun `Authorization` n'est relayé. Échec d'obtention du jeton : `502` ProblemDetails `CALCUL_INDISPONIBLE`, sans détail. Les autres routes relaient toujours le jeton entrant tel quel ; `/health/calcul` n'échange rien. Débit : limite nommée `calcul` (`RateLimit__Calcul__PermitLimit`, 60 requêtes/min), partitionnée par `oid`, celui de l'application MCP : elle est donc **commune à tous les gestionnaires** (assumé en V1), en plus de la limite globale. « Seule la gateway » désigne l'identité managée de la **Container App principale**, qui ne contient plus que la gateway (#70) : rag a sa propre Container App et son identité (`uami-insurflow-rag-app`), underwriting-admin sa propre Container App sans identité utilisateur. `GET /health/calcul` est anonyme, sans limite de débit, et vise `/api/sante` de la Function.

## Configuration

| Variable | Défaut | Rôle |
|---|---|---|
| `ReverseProxy__Clusters__rag__Destinations__d1__Address` | `http://localhost:8001` | Adresse de `rag` (compose : `http://rag:8001`) |
| `ReverseProxy__Clusters__underwriting__Destinations__d1__Address` | `http://localhost:8002` | Adresse d'`underwriting-admin` |
| `Entra__TenantId` | **obligatoire** | Tenant Entra (émetteurs v1 et v2 acceptés) |
| `Entra__Audiences__rag__0` | **obligatoire** | Audiences de `rag`, en liste « a, b » : la même valeur que `RAG_API_AUDIENCES`, lue par `rag` (`<ID client>,api://<ID client>`) |
| `Entra__Audiences__underwriting__0` | **obligatoire** | Audiences d'`underwriting-admin`, en liste « a, b » (`UNDERWRITING_API_AUDIENCES`) |
| `ReverseProxy__Clusters__mcp__Destinations__d1__Address` | `http://localhost:8003` | Adresse de `serveur-mcp` (compose : `http://serveur-mcp:8003` ; Azure : `https://<app MCP>.internal.<domaine de l'environnement>`, sa propre Container App à entrée interne) |
| `Entra__Audiences__cluster__0` | `api://agentinsurflow-cluster` | Audiences du cluster d'agents, en liste « a, b » (compose : `CLUSTER_API_AUDIENCES`) |
| `Entra__Audiences__mcp__0` | `api://agentinsurflow-mcp` | Audiences de `serveur-mcp`, en liste « a, b » |
| `ReverseProxy__Clusters__calcul__Destinations__d1__Address` | `http://localhost:7071` | Adresse de la Function de calcul (compose : `http://calcul:80` ; Azure : `${CALCUL_URL}`) |
| `Calcul__Portee`, `Calcul__IdentiteClientId` | _(vide)_ | Portée du jeton de la gateway pour la Function (`api://<appId calcul>/.default`) et client id de son identité managée ; sans portée, aucun jeton relayé |
| `Entra__Audiences__calcul__0` | `api://agentinsurflow-calcul` | Audiences de la Function de calcul, en liste « a, b » (compose : `CALCUL_API_AUDIENCES` ; Azure : `${CALCUL_AUDIENCE}`) |
| `Proxy__EnvoyDevant` | `false` | `true` en Azure : IP réelle reprise de l'envoy |
| `RateLimit__Global__PermitLimit`, `RateLimit__Reponses__PermitLimit`, `RateLimit__Mcp__PermitLimit`, `RateLimit__Calcul__PermitLimit`, `RateLimit__Cluster__PermitLimit`, `RateLimit__Llm__PermitLimit`, `RateLimit__FenetreSecondes` | `120`, `10`, `60`, `60`, `10`, `30`, `60` | Limitation de débit |
| `SWAGGER_CLIENT_ID` | vide | Client Entra public de la page Swagger |
| `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | `http://localhost:8002/v1/traces` | Récepteur OTLP des traces (Azure : `https://<FQDN interne d'underwriting-admin>/v1/traces`) |
| `Telemetrie__Audience` | (vide) | `api://<appId underwriting>` : la gateway envoie ses traces avec un jeton d'application (portée `<audience>/.default`, rôle `Telemetrie`, même credential que `calcul` et `llm`). Vide (local, compose) : export sans jeton. Échec d'obtention du jeton : export sans en-tête (401 côté récepteur), jamais de blocage ni de jeton journalisé |
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
docker run --rm -p 8000:8000 -e Entra__TenantId=<tenant> \
  -e Entra__Audiences__rag__0=api://agentinsurflow-rag \
  -e Entra__Audiences__underwriting__0=api://agentinsurflow-underwriting \
  agentinsurflow-gateway:local
open http://localhost:8000/    # page Swagger
```

## Tests — forme « diamant »

La gateway n'a presque aucune logique isolable (routes et politiques sont déclaratives) : ses tests sont des **tests d'intégration** (`WebApplicationFactory` devant deux backends **WireMock.Net**, jetons signés par une clé RSA de test à la place des métadonnées du tenant, sans appel réseau à Entra), pas des tests unitaires de configuration. C'est l'exception prévue par la pyramide de la solution (70 % TU / 20 % TI / 10 % E2E sur `rag` et `underwriting-admin`) ; les tests de la gateway sont comptés à part.

| Test | Ce qu'il prouve |
|---|---|
| `Route_vers_le_bon_backend` (11 cas) | Chaque ressource REST atteint le bon service, avec le bon chemin, et pas l'autre |
| `Chemin_non_route_404_sans_appel_backend` (6 cas) | Ni route fourre-tout, ni anciennes routes RPC (`/api/agent`, `/v1/ingestion`, `/internal/…`) |
| `Transmet_XForwardedFor_reecrit`, `XForwardedPrefix_du_client_ne_passe_pas` | Les en-têtes `X-Forwarded-*` du client n'atteignent pas les services (règle S3-21) |
| `Documentation_recoit_son_prefixe_public` | `/rag` et `/underwriting` transmis en `X-Forwarded-Prefix` |
| `Transmet_Authorization_et_traceparent_sans_les_modifier` | Jeton et contexte de trace transmis intacts |
| `Sans_jeton_401_…` (9 cas), `Jeton_signe_par_une_autre_cle_401`, `Jeton_expire_401`, `Emetteur_d_un_autre_tenant_401` | Jeton absent ou invalide : 401 `NON_AUTHENTIFIE`, rien n'est transmis |
| `Role_manquant_403`, `Audience_d_un_autre_service_403`, `Role_Telemetrie_ne_donne_pas_les_contrats_403` | Rôle ou audience insuffisant : 403 `ACCES_REFUSE` |
| `Bon_role_et_bonne_audience_transmis` (9 cas), `Jetons_v1_et_v2_acceptes` | Le bon jeton passe, sur chaque route |
| `Documentation_et_sante_sans_jeton`, `Chemin_inconnu_401_sans_jeton_404_avec_jeton`, `Toutes_les_routes_declarent_une_politique` | Exceptions publiques et refus par défaut |
| `Au_dela_de_la_limite_globale_429_RetryAfter_ProblemDetails`, `Limite_par_utilisateur`, `Reponses_limite_plus_stricte`, `Sans_jeton_partition_par_ip`, `Sante_jamais_limitee` | Débit : 429 propre, budgets séparés, sondes épargnées |
| `EnvoyDevant_IP_reelle_transmise`, `EnvoyDevant_partitionne_par_IP_reelle` | Derrière l'envoy, seule la dernière entrée de `X-Forwarded-For` compte |
| `Racine_redirige_vers_la_page_swagger`, `Page_swagger_liste_les_trois_documents`, `Page_swagger_se_connecte_a_Entra_en_PKCE` | La page Swagger unique et sa connexion |
| `OpenApi_de_la_gateway_documente_health`, `Health_*` | Document OpenAPI et santé |

## Architecture

Clean Architecture **sans couche artificielle** (`~/.claude/rules/csharp-clean-architecture.md`) : un proxy pur n'a ni domaine ni cas d'usage, donc un seul projet `Api` (`Program.cs` + routes déclaratives) et un projet de tests sous `tests/`, rattaché au dossier de solution `/tests/` du `.slnx`.

```
gateway/
├── AgentInsurFlow.Gateway.slnx
├── src/AgentInsurFlow.Gateway.Api/      Program.cs · appsettings.json · appsettings.Routes.json
├── tests/AgentInsurFlow.Gateway.Api.Tests/   RoutageTests.cs · AutorisationTests.cs · DebitTests.cs · IpClientTests.cs · SwaggerTests.cs · JetonsDeTest.cs
├── Dockerfile · Makefile · README.md
```

## Déploiement

**Six Container Apps par environnement** : la principale (`infra/containerapp.yaml`, la gateway seule, 8000, **seule entrée externe**), celle d'underwriting-admin (`infra/containerapp-underwriting.yaml`, entrée interne 8002 ; cluster `underwriting` et traces de la gateway visent `https://<FQDN interne>`, lu par `deploy.yml`), la base annexe `postgres` (`infra/containerapp-postgres.yaml`, entrée TCP interne 5432, base éphémère), celle du serveur MCP (`infra/containerapp-mcp.yaml`) celle du **cluster d'agents** (`infra/containerapp-cluster.yaml`, entrée interne, identité managée propre) et celle de **rag** (`infra/containerapp-rag.yaml`, entrée interne 8001, identité managée propre). Le cluster `rag` de la gateway vise `https://<FQDN interne de rag>` (`deploy.yml` le lit) ; le cluster `llm` vise Foundry (`FOUNDRY_ENDPOINT`), joint seulement par la gateway avec son identité managée (`Calcul__IdentiteClientId`), `Llm__Portee` et les audiences `Entra__Audiences__llm__0/__1`. `deploy.yml` substitue les images et les variables dans chaque modèle, puis `az containerapp update --yaml` : base annexe, underwriting-admin, MCP, principale (gateway), puis rag (la base repart vide à chaque déploiement, ses clients y jouent leurs migrations ensuite). **Rollback** : les 4 images du SHA de la révision précédente (lu sur l'image de sa gateway).

**Une fois, à la main (Acerola), avant le premier déploiement** : `make annexe` (image annexe + secrets PostgreSQL), `make entra DOMAINE=aibrokerflow.fr` (inscriptions `agentinsurflow-rag` et `agentinsurflow-underwriting`, rôles, redirections Swagger), `make llm` (canal LLM : inscriptions `agentinsurflow-llm` et `agentinsurflow-gateway-local`, Foundry sans clé), puis les variables GitHub affichées (`RAG_API_CLIENT_ID`, `UNDERWRITING_API_CLIENT_ID`, `LLM_AUDIENCE`, `LLM_API_CLIENT_ID`, `FOUNDRY_ENDPOINT`, `AZURE_UAMI_RAG_CLIENT_ID`…, voir `docs/secrets.md`).

**Fumée (porte bloquante)**, par la gateway : `/health` et `/health/rag` donnent le SHA déployé ; `POST /api/reponses` sans jeton → 401.

**IP publique (#10)** : IP statique entrante de l'environnement `cae-insurflow` : `4.225.231.167` (`az containerapp env show --query properties.staticIp`). Seule la gateway a une entrée externe ; derrière l'envoy d'Azure, elle reprend l'IP réelle du client (`Proxy__EnvoyDevant=true`).

### Domaine personnalisé (G4, S3-28, issue #12)

`make domaine DOMAINE=<domaine>` (Acerola, une fois) lie le domaine à l'entrée de la Container App de production, donc il reste valable quand la gateway devient l'entrée. Le script affiche les enregistrements DNS à créer (sous-domaine : `CNAME` vers le FQDN de l'app ; apex : `A` vers l'IP statique de l'environnement ; dans les deux cas `TXT asuid.<domaine>`), attend leur résolution, puis lie le nom avec un certificat managé. Il ne fait rien si le nom est déjà lié.

Ensuite : variable GitHub `PROD_URL=https://<domaine>` ; la fumée de production passe alors par le domaine et vérifie son certificat. L'URI de redirection Swagger `https://<domaine>/oauth2-redirect.html` est ajoutée en G5 (`infra/entra.sh`).
