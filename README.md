# AgentInsurFlow — monorepo (v0.6.0)

Assistant des **gestionnaires d'assurance auto** : une **gateway** (seule entrée publique) devant ses services,
**underwriting-admin** (dossiers minimisés et référentiel SQL des traces), **rag**, qui ingère le **Code des assurances** depuis Légifrance, le cherche (recherche hybride pgvector) et répond par un
**agent à réponses citées**, et le **cluster d'agents** (Saga déterministe et quatre sous-agents, revue humaine du gestionnaire). Les modèles sont des déploiements **Azure AI Foundry** (API v1 compatible OpenAI), un par usage : rag sur `Kimi-K2.5` (`rag/llm.env`), le cluster sur `gpt-4.1-mini` par agent (`agentic-cluster/agents.toml`). Le tout est
livré par une **chaîne GitHub Actions CI/CD/Evals bloquante** jusqu'à la production (Azure Container Apps).

Toutes les API sont **REST** et consultables dans **une seule page Swagger**, servie à la racine de la gateway. Les gestionnaires travaillent dans l'**espace gestionnaire**, servi par la gateway sous `/app/` : [`docs/espace-gestionnaire.md`](docs/espace-gestionnaire.md).

```mermaid
flowchart LR
    PR(["👤 PR"]) --> L(["🧹 lint<br/>ruff + mypy"]) --> T{{"🛡️ test<br/>couverture ≥ 80 %"}}
    PR --> G{{"🛡️ gateway<br/>TI .NET ≥ 80 %"}}
    PR --> I{{"🛡️ integration<br/>compose + TI rag et underwriting-admin"}}
    T -- "✔" --> M(["👤 merge main"])
    G -- "✔" --> M
    I -- "✔" --> M
    M --> B(["📦 build<br/>images rag + underwriting + gateway → ACR :sha"]) --> S(["🚀 staging"]) --> FS{{"🛡️ fumée"}}
    FS -- "✔" --> EV{{"🛡️ evals<br/>si déclencheur"}}
    EV -- "✔ ou sautées" --> E2E{{"🛡️ e2e-staging<br/>E2E_STRICT"}}
    E2E -- "✔" --> R(["🏷️ release<br/>tag vX.Y.Z"])
    R --> P(["🌐 production"]) --> FP{{"🛡️ fumée"}}
    T -- "✘" --> X(["⛔ chaîne arrêtée<br/>merge refusé"])
    P -. "make rollback (1 opération)" .-> RB(["↩️ images précédentes"])
    classDef plat fill:#1E3A8A,stroke:#1E3A8A,color:#fff
    classDef ok fill:#DCFCE7,stroke:#15803D,color:#14532D
    classDef ko fill:#FEE2E2,stroke:#B91C1C,color:#7F1D1D
    classDef gate fill:#EDE9FE,stroke:#7C3AED,color:#3B0764
    class PR,M,P plat
    class L,B,S,R ok
    class X,RB ko
    class T,G,I,FS,E2E,EV,FP gate
```

Un merge sur `main` relance `lint`, `test` et `gateway` avant `build`. Les evals (portes : réussite ≥ 80 % et latence
p95 ≤ 30 s) ne tournent que si le prompt, un jeu d'évaluation, l'instantané du corpus ou la version du LLM changent
(voir *Évaluer l'agent*). `e2e-staging` passe **après** les evals (sautées ou non) : même identité de CI, donc même
quota `/api/reponses` à la gateway (#188). Le job `evals-pr` (avant merge) rejoue les jeux de la PR contre staging : voir [`docs/ci-evals.md`](docs/ci-evals.md).

## État au 29/10 (release v0.6.28)

| Projet | Langage | Rôle | État |
|---|---|---|---|
| [`gateway/`](gateway/README.md) | C# · YARP · .NET 10 | **Seule entrée publique** : routage, jeton Entra + rôle par route, limitation de débit, Swagger unique ; échange de jeton vers la Function de calcul (`/api/calcul`) et Foundry (`/api/llm`, tokens mesurés) | ✅ déployée (staging, production), seule dans la Container App principale ; domaine personnalisé en production |
| [`rag/`](rag/README.md) | Python · hexagonal | Corpus Légifrance (ingestion, dédup, versions), recherche hybride, agent à 3 verrous, attribution Etalab 2.0 | ✅ déployé ; jeu agrégé `data/aggregated/corpus-2026-10-27.json` (Code des assurances : 119 articles lus, 107 insérés, 12 abrogés rejetés ; 4 notices produits ; 6 procédures internes citant le barème) réingéré à chaque déploiement (#52, #99, [preuves](eval/preuves/)) ; `make ingest` refuse un instantané hors périmètre (#189) |
| [`underwriting-admin/`](underwriting-admin/README.md) | C# · Clean Architecture · .NET 10 | Dossiers (vue minimisée, BOLA) et référentiel SQL des traces OpenTelemetry (`/v1/traces`, `/api/traces/{trace_id}`) ; relances et classement sans suite (#136) ; contrat imprimé et fiche du lead (exceptions à la minimisation, #139) ; stockage opaque des points de reprise du cluster (schéma `points_reprise`, D106, #167) | ✅ déployé dans sa Container App (entrée interne) ; écritures brouillon/statut pour le serveur MCP (#66) ; OBO pré-autorisé (#47) |
| [`serveur-mcp/`](serveur-mcp/README.md) | Python · hexagonal | Outils MCP du cluster d'agents (`search_rag`, `get_contrat`, `evaluer_risque`, `calculer_prime`, `enregistrer_brouillon`, `update_statut_dossier`), matrice `azp` × outil | ✅ déployé dans sa Container App (entrée interne, identité propre), v0.6.0 (#15, #66) |
| [`agentic-cluster/`](agentic-cluster/README.md) | Python · hexagonal · LangGraph | Cluster d'agents (la Saga, automate déterministe sans LLM, puis Pièces, Analyste, Rédacteur, Actuaire) : évalue un dossier, écrit un brouillon, attend la revue du gestionnaire ; garde-fous LLM Guard ; joint MCP et LLM par la gateway | ✅ déployé (staging, production) dans sa Container App (entrée interne, `infra/containerapp-cluster.yaml`) depuis le 24/10 (#116) ; réglage par agent dans `agents.toml` (#117) ; recette des K jouée en staging depuis l'espace gestionnaire (27/10, [preuves](eval/preuves/recette-k-2026-10-27-staging.md)) ; état du contrat : [`docs/contrat-personnel.md`](docs/contrat-personnel.md) ; points de reprise par la gateway, plus d'accès PostgreSQL (D106, #167) |
| [`fonction-calcul/`](fonction-calcul/README.md) | Python · Azure Functions | Risque (`bareme-2026.10-v1`) et prime (`formule-2026.10-v1`) déterministes ; n'accepte que la gateway | ✅ déployée (Flex Consumption, staging et production), v0.6.0 (#64, #74) ; une instance toujours prête depuis le 28/10 (`infra/calcul.sh` ①b, #146) : plus de démarrage à froid ; fréquence du GLM Poisson freMTPL2 en comparaison (`/api/frequence`, porte de qualité en CI, #168) |
| [`e2e/`](e2e/README.md) | Python · pytest | Parcours bout en bout par la gateway (compose ou staging) | ✅ ; job `e2e-staging` bloquant avant la release |

> **Pyramide au 29/10** : 75 % TU / 24 % TI / 2 % E2E (cible 70 / 20 / 10) ; le job `pyramide` est **bloquant**
> en CI depuis #48.

> **Production et staging** : release **`v0.6.28`** au SHA `4e8a5e6` (#195), déployée le 29/10 ; la version de la
> solution (0.6) reste fixée par Acerola, le dernier chiffre est celui de la release. Depuis v0.6.26 (`d56a01e`, #193) :
> synchronisation de la doc (v0.6.27, #194) et test du rejeu d'un 401 par l'espace gestionnaire (v0.6.28, #195). **Livraison du 29/10** (v0.6.25,
> PR groupée #185, puis #188 → #193) : pyramide bloquante (#48), `evals-pr` réactivé contre staging (#55), barème
> citable et jeu agrégé unique (#99, #52), scraping des notices `/notices/` et extraction big data PySpark (#45, #51),
> base annexe recréée à chaque run et alerte AL-10 (#186), `e2e-staging` après les evals (#188), refus d'un instantané
> hors périmètre (#189) et rejeu unique d'une réponse lente avant la porte p95 (#192). **Sprint 5 « la vigie »** (#151 → #157),
> livré en un seul déploiement (#171) : export **Application Insights** en plus de l'OTLP sur les cinq services et la
> Function, numéro de contrat masqué dans les spans HTTP (#158, #161, #65) ; tableau de bord `vigie-<env>` et alertes
> AL-1 → AL-10 (#162) ; [`docs/exploitation.md`](docs/exploitation.md) : déployer, surveiller, diagnostiquer, revenir en
> arrière (#163) ; points de reprise de la Saga par la gateway, suppression de D26 (D106, #167) ; GLM Poisson de fréquence
> à côté du barème (#168) ; bilan du contrat personnel, amendement P45 et grille de retours (#170) ; scénario de la démo
> des 10 minutes ([`docs/demo-sprint5.md`](docs/demo-sprint5.md), #173). Déploiement : Container Apps lancées ensemble
> après la base annexe (#172), reconnexion Azure avant l'ingestion du corpus (#164, #174). Avant, depuis le 26/10 :
> l'espace gestionnaire `/app/` (#134), les relances et `SANS_SUITE` (#136), `make recette` (#137, #149), `make entra`
> qui garde les agents pré-autorisés sur le MCP (#138), le contrat imprimé et la fiche du lead (#139), les tokens par
> étape (#140), les pictogrammes (#142), la visionneuse du contrat (#145), les délais de l'évaluation (#146) et les liens
> de l'en-tête au clavier (#147). Le cluster exporte vers Application Insights (compteurs et métriques
> `agentic-cluster` présents) mais aucune évaluation authentifiée ne l'a atteint depuis le 28/10 (encore vrai le 29/10 en v0.6.26) : ses spans et
> `audit.*` restent à prouver par une évaluation réelle (#176). **Bases éphémères** : chaque
> déploiement remet les dossiers de staging et de production au seed ([`docs/rollback.md`](docs/rollback.md)).
> Historique (v0.6.0, du 22/10 au 26/10) : le cluster d'agents (#92, production depuis le 24/10 par #116),
> le job `test` limité aux TU (#93), le cache Docker inline depuis l'ACR (#95), l'audience `api://agentinsurflow-cluster` (#96),
> l'isolement du cluster (le frontal Container Apps répond 404 à une application interne, #97), `E2E_CONTRAT_AUTRE` (#102),
> le cluster sur `gpt-4.1-mini` (#105), la Saga sans rôle LLM (#106) et son nom (#107), les limites de débit par `oid` et `azp` (#116),
> `agents.toml` (#117) et la vérification du pool du point de reprise (#118). `/health` et `/health/{rag,underwriting,mcp,cluster}` servent
> la même release, `/health/calcul` le barème et la formule. #98 (notices du contrat type) et #47 (OBO) sont fermées ;
> reste à vérifier en production la mesure des tokens par la gateway (#71).
> Evals de staging à **100 %** (11/11, porte 80 %), latence p95 **14,9 s** (max 30 s), manifeste
> `manifeste-0.6.0-build.130` (27/10, #50) : annexe bonus-malus rattachée à A121-1, réponses résumées
> ([`eval/preuves/evals-2026-10-27.json`](eval/preuves/evals-2026-10-27.json)).

Le contrat REST (ressources, méthodes, codes) et la correspondance avec les noms d'endpoints du brief sont dans
[`gateway/README.md`](gateway/README.md#contrat-rest-s3-24) ; le détail des routes de `rag` (rôles, erreurs, contrat
d'ingestion, agent) dans [`rag/README.md`](rag/README.md). Tests : pyramide **70 % TU / 20 % TI / 10 % E2E**
(règle [`.claude/rules/testing-pyramid.md`](.claude/rules/testing-pyramid.md), porte `make pyramide`).

### Architecture déployée

Chaque environnement (staging, production) est **six Container Apps** du même environnement : la principale, qui ne contient que la **gateway**
([`infra/containerapp.yaml`](infra/containerapp.yaml)), celle d'**underwriting-admin** ([`infra/containerapp-underwriting.yaml`](infra/containerapp-underwriting.yaml), entrée interne), celle du **serveur MCP**
([`infra/containerapp-mcp.yaml`](infra/containerapp-mcp.yaml)), celle du **cluster d'agents** ([`infra/containerapp-cluster.yaml`](infra/containerapp-cluster.yaml), entrée interne, `ai-cluster-{staging,production}`), celle de **rag** ([`infra/containerapp-rag.yaml`](infra/containerapp-rag.yaml)), à entrée interne et identité managée propre, que seule la gateway appelle, et celle de la **base PostgreSQL annexe** ([`infra/containerapp-postgres.yaml`](infra/containerapp-postgres.yaml)), à entrée TCP interne 5432.
**Foundry n'est joint que par la gateway** (route `/api/llm`, clés désactivées) : rag et les quatre sous-agents du cluster lui demandent le modèle avec un jeton d'application (rôle `LLM`) ; la Saga n'a pas de LLM.
La Function de calcul (Azure Functions) n'accepte que la gateway :

| Conteneur | Port | Rôle |
|---|---|---|
| `gateway` | 8000 | **seul exposé** (entrée de la Container App) ; valide jeton et rôle, puis transmet |
| `rag` | 8001 | **sa propre Container App** (interne) : API du corpus et de l'agent ; revalide le jeton ; migrations de la base au démarrage (`rag/demarrer.sh`) ; joint la base annexe (sa Container App, TCP interne 5432), le modèle et les dossiers par la gateway |
| `underwriting-admin` | 8002 | **sa propre Container App** (interne, sans identité managée utilisateur) : dossiers (`/api/contrats`, BOLA) et traces (`/v1/traces`, `/api/traces/{trace_id}`) ; revalide le jeton ; migrations EF Core au démarrage |
| `postgres` | 5432 | **sa propre Container App** (TCP interne) : **base annexe éphémère** (pgvector) : bases `vecteurs`, `dossiers`, `traces` ; une réplique, sans volume |

Documentation des données : [`docs/donnees/`](docs/donnees/) — [sources](docs/donnees/sources.md),
[pipeline](docs/donnees/pipeline.md), [modèle Merise](docs/donnees/modele.md), [SQL](docs/donnees/requetes-sql.md),
[RGPD](docs/donnees/rgpd.md), [recherche](docs/donnees/recherche.md), [traces](docs/donnees/traces.md) (SQL pour l'espace gestionnaire et l'E2E, Application Insights pour la vigie : double export en Azure) ;
OpenAPI : [`docs/openapi/`](docs/openapi/) (`make openapi`) ; démo : [`docs/demo-atelier-3.md`](docs/demo-atelier-3.md), [`docs/demo-atelier-4.md`](docs/demo-atelier-4.md), [`docs/demo-sprint5.md`](docs/demo-sprint5.md) ; contrat personnel K1→K11 : [`docs/contrat-personnel.md`](docs/contrat-personnel.md) ;
exploitation : [`docs/exploitation.md`](docs/exploitation.md) ; amendements du dossier : [`docs/dossier/amendements.md`](docs/dossier/amendements.md) ; retours des ateliers : [`docs/grille-retours.md`](docs/grille-retours.md).

La base annexe repart **vide à chaque nouvelle révision** (déploiement ou rollback) : les migrations la recréent au
démarrage, puis `deploy.yml` réingère le dernier instantané versionné de `data/raw/` (rôle `Ingestion` de la CI).

## Arborescence

```text
.
├── rag/                       # 🐍 service rag (Python, hexagonal) — README, pyproject, Dockerfile, llm.env
│   ├── agentinsurflow_rag/    #   domain/ · application/ · infrastructure/ · api/ · cli/ · prompts/systeme.md
│   ├── migrations/            #   Alembic, arbre « vecteurs » (SQL écrit à la main), rejoué au démarrage
│   ├── demarrer.sh            #   point d'entrée du conteneur : migrations, puis uvicorn
│   └── tests/                 #   unit/ (TU, sans I/O) · integration/ (TI) · fakes.py (doublures des ports)
├── agentic-cluster/           # 🤖 cluster d'agents (Python, hexagonal, LangGraph) — README, agents.toml (réglage par agent), Dockerfile
├── serveur-mcp/ · fonction-calcul/ · underwriting-admin/  # outils MCP · Function de calcul · dossiers et traces (README chacun)
├── e2e/                       # parcours bout en bout par la gateway
├── gateway/                   # 🚪 gateway YARP (C#, .NET 10) — README, Makefile, Dockerfile, src/, tests/
├── tests/unit/                # tests de l'outillage de la racine (tools/)
├── tools/evals.py             # make eval / make calibrer : golden set + jeu de démo contre une API, manifeste
├── tools/pyramide.py          # make pyramide : porte 70 / 20 / 10
├── tools/version.py           # release vX.Y.Z d'après les tags
├── data/raw/                  # instantanés Légifrance (code-assurances-<date>.json, manifeste + sha256)
├── docker-compose.yml         # make up : postgres + rag (:8001) + underwriting-admin (:8002) + serveur MCP + cluster d'agents + calcul + gateway (:8000)
├── CLAUDE.md                  # contrat transverse du monorepo (non-négociables, pyramide, versions)
├── .github/workflows/
│   ├── ci-cd.yml              # lint · test · gateway → [evals-pr] · build → staging → [evals] → release → production
│   └── deploy.yml             # déploiement (modèle containerapp.yaml) + fumée ; lancé à la main = rollback
├── infra/
│   ├── bootstrap.sh           # make infra : groupe de ressources, ACR, Container Apps, OIDC (idempotent)
│   ├── containerapp.yaml      # modèle de la Container App principale : la gateway seule
│   ├── containerapp-underwriting.yaml  # modèle de la Container App d'underwriting-admin (interne, 8002)
│   ├── containerapp-postgres.yaml  # modèle de la base annexe (TCP interne 5432)
│   ├── containerapp-rag.yaml  # modèle de la Container App de rag (interne, identité propre) ; idem containerapp-mcp.yaml
│   ├── llm.sh                 # make llm : Entra llm + gateway-local, Foundry sans clé, rôle réservé à la gateway
│   ├── domaine.sh             # make domaine : domaine personnalisé de la production (certificat managé)
│   ├── entra.sh               # make entra : inscriptions Entra des API et rôles d'application
│   ├── postgres/ · postgres-annexe.sh  # make annexe : image PostgreSQL annexe et secrets des Container Apps
│   └── protection-main.json   # make proteger : checks exigés sur main
├── docs/                      # secrets, rollback ; preuves et démo de l'atelier du sprint 2
├── eval/
│   ├── golden.jsonl           # cas d'évaluation de l'agent (versionnés)
│   ├── questions-demo.jsonl   # jeu de démo (questions de gestionnaires, BOLA)
│   ├── preuves/               # journaux de chaîne, rapports d'evals et d'ingestion versionnés
│   └── ateliers/              # grille de l'atelier croisé n°2
├── Makefile                   # orchestre : lint, test, up, ingest, eval, infra… ; gateway-<cible> → gateway/
├── pyproject.toml · uv.lock   # espace de travail uv (membres : rag, serveur-mcp, fonction-calcul, agentic-cluster) ; version de la solution (0.6.0)
├── global.json · Directory.Build.props  # SDK .NET 10 et règles communes des projets C#
├── .python-version
└── .env.example               # toutes les clés, sans valeurs
```

| Python | Équivalent .NET |
|---|---|
| `pyproject.toml` + `uv.lock` | `.csproj` + `packages.lock.json` |
| `uv sync --locked` | `dotnet restore --locked-mode` |
| FastAPI + `Depends` | Minimal API + injection de dépendances |
| `DepotCorpus` (`Protocol`, `domain/ports.py`) | `interface IDepotCorpus` |
| `app.dependency_overrides` | remplacer un service dans `WebApplicationFactory` |
| `pydantic-settings` | `IOptions<T>` lié à la configuration |
| Alembic (`make migrate`) | migrations EF Core (`dotnet ef database update`) |

## Lancer (en local)

Prérequis : [uv](https://docs.astral.sh/uv/) et Docker ; SDK .NET 10 (`global.json`) pour `make openapi` et les
tests C# hors Docker.

```bash
cp .env.example .env      # remplir LLM_AUDIENCE, RAG_CLIENT_SECRET, AZURE_TENANT_ID, RAG_SEUIL, PG_*_PASSWORD…
make install              # dépendances figées par uv.lock
make up                   # postgres + rag (:8001) + underwriting-admin (:8002) + serveur MCP + cluster d'agents + calcul + gateway (:8000) → http://localhost:8000/ : Swagger unique
make down                 # arrête tout et vide la base annexe
make run                  # rag seul, sans Docker : http://localhost:8000 → Swagger de rag
```

Dans la **page Swagger unique** de la gateway (`http://localhost:8000/`), le menu donne les 3 documents OpenAPI ;
« Authorize » se connecte à Entra (PKCE) et « Try it out » appelle les routes REST publiques de la gateway, avec
jeton, rôle (`Gestionnaire`, `Ingestion`) et limite de débit.

**Corpus** : `make up` crée la base et ses migrations ; il reste à la remplir.

```bash
make extraire                                    # Légifrance (bac à sable PISTE) → data/raw/code-assurances-<date>.json
make bareme                                      # instantané du barème → data/raw/bareme-<version>.json
make agreger                                     # Légifrance + barème + documents rédigés → data/aggregated/corpus-<date>.json (#52)
make ingest JEU=data/aggregated/corpus-<date>.json   # jeu agrégé unique → POST /api/ingestions
make ingest INSTANTANE=data/raw/code-assurances-<date>.json   # ou rejeu d'un seul instantané Légifrance
make calibrer URL=http://localhost:8000          # intervalle où choisir RAG_SEUIL (porte de pertinence)
```

`POST /api/reponses` rend une **réponse citée** (`statut`, `texte`, `citations`, `trace_id`) ou un refus
`NOT_FOUND_IN_CORPUS` ; LLM injoignable ou trop lent (30 s, `LLM_DELAI_S`) : `statut = REVUE_HUMAINE` (mode dégradé,
dossier-conception-v1.md, K5). Pour un article cité, `GET /api/documents/{doc_id}/attribution` donne ses mentions
**Etalab 2.0** (concédant DILA, licence, date de l'instantané). Détails : [`rag/README.md`](rag/README.md).

**Authentification au LLM** : **aucune clé**. rag appelle le LLM **par la gateway** (`AZURE_OPENAI_ENDPOINT` =
`${GATEWAY_URL}/api/llm`, `http://gateway:8000/api/llm` dans le compose) avec un jeton d'**application** pour
l'audience `LLM_AUDIENCE` (rôle `LLM`) : secret de l'inscription rag (`RAG_CLIENT_SECRET`) en local, identité
managée fédérée (`AZURE_UAMI_CLIENT_ID`) en Azure, comme l'OBO. La gateway échange son propre jeton avec Foundry.
Le modèle de rag (`Kimi-K2.5`) est épinglé dans `rag/llm.env` ; celui du cluster (`gpt-4.1-mini`), par agent, dans `agentic-cluster/agents.toml`.

## Tester

```bash
make lint                 # ruff (style) + mypy (typage strict)
make test                 # TU (sans Docker) : rag/tests/unit + outillage
make test-integration     # TU + TI contre le PostgreSQL du compose, couverture ≥ 80 % (job CI « test »)
make pyramide             # porte 70 / 20 / 10 (S3-22)
make gateway-test         # gateway : TI + couverture ≥ 80 % (job CI « gateway »)
```

Les jobs `lint`, `test` et `gateway` **mockent toujours le LLM** (`FakeLLM`, HTTP simulé) : aucun secret ni appel
réel. Seules les **evals** appellent le vrai modèle.
La couverture visée est la fourchette **80–83 %** ; la porte bloquante est sa borne basse (80 %, `pyproject.toml`).

## Évaluer l'agent (evals)

```bash
make eval                               # contre l'API locale (jeton : EVALS_JETON)
make eval URL=https://<staging>         # contre un environnement déployé
```

`tools/evals.py` rejoue `eval/golden.jsonl` et `eval/questions-demo.jsonl` en boîte noire : seuls
`POST /api/reponses`, `GET /api/extraits` et `/health` sont appelés, avec un jeton Entra de rôle `Gestionnaire`.
Chaque cas passe des contrôles déterministes, et la latence est mesurée :

| Contrôle | Vérifie |
|---|---|
| `http` | Le code HTTP attendu (200, ou 404 pour un dossier hors portefeuille : BOLA) |
| `statut` | Le statut attendu (`OK`, `NOT_FOUND_IN_CORPUS`…) |
| `articles` | Au moins un des articles attendus est cité |
| `mode_llm` | Pour une réponse attendue, le LLM a vraiment répondu (pas de repli) |
| `non_vide` | La réponse n'est pas vide |
| `longueur` | La réponse est bornée, y compris sous injection |
| **latence p95** | ≤ 30 s (dossier-conception-v1.md, D11) |

Porte : taux de réussite ≥ **80 %** (seuil de départ, `🔴 à calibrer`) **et** latence p95 ≤ 30 s.
Un cas en 429, hors délai client (`http 0`) ou au-dessus de 30 s est **rejoué une fois** : la porte juge la
réponse rejouée, et une lenteur qui se répète la fait toujours échouer (#192).

**Déclenchement** : les evals ne tournent que si un fichier susceptible de changer leur résultat a changé
**depuis le dernier manifeste validé** (tag `manifeste-X.Y.Z-build.N`, job `changements`) ; sinon elles sont
sautées et la chaîne continue. Un manifeste dont les evals ont échoué n'est jamais tagué : le commit suivant
le réévalue, même s'il ne touche pas ces fichiers. Sans aucun tag `manifeste-*`, les evals tournent.

| Déclencheur | Fichier versionné |
|---|---|
| Prompt | `rag/agentinsurflow_rag/prompts/` |
| Jeux d'évaluation | `eval/golden.jsonl`, `eval/questions-demo.jsonl` |
| Instantané du corpus | `data/raw/` |
| Version du LLM | `rag/llm.env` (`AZURE_OPENAI_DEPLOYMENT`, épinglé et copié dans l'image) |

| Job | Quand | Contre quoi | Jeton |
|---|---|---|---|
| `evals-pr` | PR (déclencheurs modifiés, libellé `evals`) ou `workflow_dispatch` depuis `main` | **staging** (code de `main`) avec les jeux d'évaluation de la PR | Entra par **OIDC**, rôle `Gestionnaire` de la CI ; résumé commenté sur la PR ([`docs/ci-evals.md`](docs/ci-evals.md)). Sauté, il satisfait la protection de `main` |
| `evals` | merge, avant la production | **staging** déployé, corpus réingéré par `deploy.yml` ; cas à `numero_contrat` écartés jusqu'à underwriting-admin (U2, `--sans-dossiers`) | Entra par **OIDC** (`api://agentinsurflow-rag/.default`) : l'identité de la CI porte le rôle `Gestionnaire` (`make entra`) |

Installation, déclenchement, limites et démonstration de `evals-pr` : [`docs/ci-evals.md`](docs/ci-evals.md).

**Artefact de chaque passage** : `evals-staging-<sha>` (onglet *Summary* du run). Le rapport JSON s'ouvre sur un
**manifeste** qui dit ce qui a été évalué :

| Champ du manifeste | Contenu |
|---|---|
| `version` | Version du manifeste : `X.Y.Z-build.N` (pyproject + n° de run GitHub) |
| `date`, `commit`, `run`, `cible` | Quand, quel commit, lien du run GitHub, URL évaluée |
| `modele` | Déploiement de rag épinglé (`rag/llm.env`) **et** modèle observé dans les réponses de l'API |
| `prompts` | Chaque prompt : fichier, empreinte sha256, contenu |
| `golden`, `questions` | Fichier, empreinte sha256, identifiants des cas |
| `corpus` | Dernier instantané ingéré et nombre de chunks (`/health`) |
| `portes` | Seuil de réussite et latence p95 maximale appliqués |

Viennent ensuite le taux, la latence p95 et le détail de chaque cas (contrôles ratés, latence, réponse,
et `rejeu` : raison et latence de la première tentative, quand le cas a été rejoué).
Exemple du sprint 2 : `eval/preuves/evals-local-2026-10-15.json`.

> 🔁 **Analogie .NET** : une suite xUnit de non-régression, sauf qu'on mesure un **taux de réussite** au lieu
> d'exiger 100 % de `Assert`, car la sortie d'un LLM n'est pas déterministe (source : dossier-conception-v1.md, §7.2).

## Déployer

Installation, à faire une seule fois (écritures Azure et Entra : lancées à la main par Acerola) :

1. `make infra` crée le groupe de ressources, l'ACR, l'environnement Container Apps et douze apps (six par environnement, staging et production : la principale, underwriting-admin, le serveur MCP, le cluster d'agents, rag et la base annexe), reprend l'application Entra `agentinsurflow` et ses 4 fédérations OIDC (`main`, `staging`,
   `production`, `pull_request`), puis attribue les rôles. Il affiche les valeurs à reporter. Attribuer des rôles
   exige *Owner* ou *User Access Administrator*.
2. `make entra` inscrit les API `agentinsurflow-rag` (rôles `Gestionnaire`, `Ingestion`) et
   `agentinsurflow-underwriting` (`Gestionnaire`, `Telemetrie`), et attribue les rôles (toi, la CI, un 2ᵉ gestionnaire).
3. `make annexe` construit l'image PostgreSQL annexe (`agentinsurflow-postgres:3`) et pose les mots de passe en
   **secrets des Container Apps** (chacune ceux dont elle se sert).
   `make llm` (après `make entra`) inscrit `agentinsurflow-llm` et `agentinsurflow-gateway-local`, désactive les clés de Foundry et réserve l'accès à la gateway.
4. `make domaine DOMAINE=…` lie le domaine personnalisé à la production (certificat managé), puis poser `PROD_URL`.
   `make vigie ENV=staging|production` (à lancer à la main, il écrit dans Azure) crée `appi-insurflow-<env>` sur le Log Analytics `workspace-svespucepZG6` (variable `LOG_ANALYTICS_WORKSPACE` du `.env`). Il pose le secret `appinsights-connection` sur les cinq Container Apps et la chaîne de connexion dans le réglage de la Function `acerolaz-calcul-<env>`. Sans ce secret, `deploy.yml` refuse le déploiement.
5. Reporter à la main les variables dans GitHub en suivant [docs/secrets.md](docs/secrets.md).
6. `git push`, puis `make proteger` : `main` n'accepte plus que des commits dont `lint`, `test`, `gateway` et
   `evals-pr` sont verts (un `evals-pr` sauté compte comme vert).

Ensuite, chaque **merge sur `main`** déclenche toute la chaîne, sans action manuelle. Trois versions :

| Version | Forme | Désigne | Où la lire |
|---|---|---|---|
| Release | `vX.Y.Z` (ex. `v0.2.0`) | le commit livré en production, tagué juste avant | `/health` → `release`, tags Git, résumé du run |
| Image | SHA du commit | les cinq images (`agentinsurflow-gateway`, `agentinsurflow-rag`, `agentinsurflow-underwriting`, `agentinsurflow-mcp`, `agentinsurflow-cluster`), même tag | `/health` (gateway), `/health/rag`, `/health/underwriting`, `/health/mcp` et `/health/cluster` → `version` |
| Manifeste | `X.Y.Z-build.N` (ex. `0.4.0-build.35`) | ce qui a été évalué : modèle, prompts, jeux d'évaluation | `/health/rag` → `manifeste`, rapport d'évaluation, tag `manifeste-…` |

Les trois versions sont calculées par le job `changements` puis **gravées dans les images** : un rollback restaure aussi
les versions affichées. X.Y se choisissent à la main dans `pyproject.toml` (`version`, fixée par Acerola : 0.6.0
depuis `feat/mcp`, release v0.6.0 ; `rag/pyproject.toml` reste en 0.4.0).

- **Release** : Z est calculé par `tools/version.py` d'après les tags (`v0.1.0`, puis `v0.1.1`…) ; passer le
  pyproject à `0.2.0` donne `v0.2.0`. En staging, `release` est la **candidate** : le tag n'est posé qu'après
  staging et evals, juste avant la production.
- **Version croissante** : hors rollback, une release livrée ne descend jamais sous la précédente. Un pyproject
  dont X.Y est sous la dernière release fait échouer `changements` ; avant la production, `deploy.yml` compare la
  release à livrer à celle en service (`/health`) et refuse une version inférieure (égale = relance du même
  déploiement ; production injoignable = refus). Seul `deploy.yml` lancé à la main (`make rollback`) revient en arrière.
- **Manifeste** : si un déclencheur a changé, nouvelle version `X.Y.Z-build.<n° du run>` (`X.Y.Z-local` hors CI),
  taguée `manifeste-…` quand les evals passent ; sinon, celle du dernier manifeste validé.

La **fumée** (bloquante, par la gateway) attend que gateway, rag **et** underwriting-admin servent le SHA attendu (rag démarre après
ses migrations), puis vérifie que `/api/reponses` répond 401 sans jeton ; le LLM est vérifié par les evals de staging.

### Ressources Azure actuelles

| Ressource | Nom | État |
|---|---|---|
| Groupe de ressources | `svespuceRG` (créé en `francecentral` ; ressources en `swedencentral`) | ✅ |
| Registre d'images | `acerolazacr` : `agentinsurflow-gateway`, `agentinsurflow-rag`, `agentinsurflow-underwriting`, `agentinsurflow-mcp`, `agentinsurflow-cluster` (tag = SHA), `agentinsurflow-postgres:3` | ✅ |
| Environnement Container Apps | `cae-insurflow` (profils de charge, sans VNet : l'entrée TCP interne de PostgreSQL n'en exige pas) | ✅ |
| Container App staging | `insurflow-staging` (principale = gateway seule) → `https://insurflow-staging.redstone-0f3be5e1.swedencentral.azurecontainerapps.io` | ✅ reçoit chaque merge |
| Container Apps par service | `insurflow-{uw,mcp,rag,pg}-{staging,production}` et `ai-cluster-{staging,production}` : entrée interne (PostgreSQL en TCP 5432, base éphémère) | ✅ |
| Function de calcul | `acerolaz-calcul-{staging,production}` (Flex Consumption, Python 3.12), stockage `acerolazcalcul` ; Easy Auth : la gateway seule | ✅ |
| Container App production | `insurflow-production` (principale = gateway seule ; underwriting, MCP, rag et PostgreSQL ont les leurs) → `https://aibrokerflow.fr` (domaine personnalisé, `PROD_URL`) | ✅ `v0.6.28` |
| Modèles | `Kimi-K2.5` (rag), `gpt-4.1-mini` (cluster, `agents.toml`) et le déploiement d'embeddings (`AZURE_OPENAI_EMBEDDING_DEPLOYMENT`) sur la ressource Foundry `svespuce-971`, **sans clé** (`disableLocalAuth`) : appelée par la gateway seule (`/api/llm`) | ✅ |
| Entra | application de la CI `agentinsurflow` + 4 fédérations OIDC ; API `agentinsurflow-rag`, `-underwriting`, `-mcp`, `-calcul`, `-llm` ; `agentinsurflow-gateway-local` (secret dans le `.env` local seulement) ; rôle `PointsDeReprise` (principal du cluster seul, D106) | ✅ |
| Vigie (`make vigie`) | `appi-insurflow-{staging,production}` sur le Log Analytics `workspace-svespucepZG6` ; groupe d'actions `ag-insurflow-<env>` (e-mail), alertes AL-1 → AL-10 (`infra/vigie/alertes.tsv`), test de disponibilité `web-sante-<env>`, tableau de bord `vigie-<env>` | ✅ |
| Identités managées | gateway `uami-insurflow-rag` (nom historique), rag `uami-insurflow-rag-app`, serveur MCP `uami-insurflow-mcp` ; underwriting-admin sans identité Azure | ✅ |
| Rôles | CI : Contributor, AcrPush, AcrPull ; « Cognitive Services OpenAI User » sur Foundry : gateway et `gateway-local` **seulement** (`make llm` retire les autres) | ✅ attribués |

## Rollback

```bash
make rollback             # production → images précédentes, en une opération
make rollback ENV=staging TAG=<sha>   # ou une version précise
```

Le rollback redéploie **gateway, rag, underwriting-admin, serveur MCP et cluster** au SHA de la révision précédente, puis réingère le corpus (base annexe
éphémère). Détails et scénario de répétition : [docs/rollback.md](docs/rollback.md).

## Preuves et atelier

| Sujet | Où |
|---|---|
| Secrets hors dépôt, report dans GitHub | [docs/secrets.md](docs/secrets.md) |
| Rollback | [docs/rollback.md](docs/rollback.md) |
| Ingestion du Code des assurances en staging (20/10, puis 27/10 avec l'annexe d'A121-1) | `eval/preuves/ingestion-2026-10-2{0,7}-staging*.json` |
| Journaux versionnés | `eval/preuves/` (`make preuve RUN=<id> NOM=<nom>`) |
| Rapport d'évaluation (manifeste + résultats) | artefact `evals-staging-<sha>` du run, à copier dans `eval/preuves/` ; dernier : `eval/preuves/evals-2026-10-27.json` (100 %, `manifeste-0.6.0-build.130`) |
| Sprint 2 : commit volontairement cassé et bloqué | [docs/preuve-blocage.md](docs/preuve-blocage.md) |
| Sprint 2 : script de la démo (20 min) | [docs/demo-atelier.md](docs/demo-atelier.md) |
| Grille de l'atelier | [eval/ateliers/sprint-2-grille.md](eval/ateliers/sprint-2-grille.md) |

## Hors périmètre actuel

Livrés depuis : le point d'entrée **MCP** par la gateway (#15), la Saga et les agents avec **validation humaine** (#7).
Pas encore : l'OCR en A2A (source : dossier-conception-v1.md) et la décision `ACCEPTE` d'un dossier complet de bout en bout (#98).
Les sujets encore ouverts (découpage des agents, protocoles…) ne sont pas présumés.
