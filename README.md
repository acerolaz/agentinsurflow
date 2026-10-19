# AgentInsurFlow — le socle et la chaîne (Sprint 2)

Squelette de bout en bout : une **API REST FastAPI** qui donne accès à **un agent** dont la réponse vient
d'un modèle **Azure AI Foundry** (`Kimi-K2.5`, appelé par l'API v1 compatible OpenAI), livrée par une
**chaîne GitHub Actions CI/CD/Evals bloquante** jusqu'à la production (Azure Container Apps). Rien de riche
fonctionnellement, mais tout est branché : ce qui suivra passera par cette chaîne.

L'interface est **Swagger UI**, servie à la racine `/`.

```mermaid
flowchart LR
    PR(["👤 PR"]) --> L(["🧹 lint<br/>ruff + mypy"]) --> T{{"🛡️ test<br/>couverture ≥ 80 %"}}
    T -- "PR" --> EP{{"🛡️ evals-pr<br/>si déclencheur"}} -- "✔ merge" --> M(["👤 merge main"])
    M --> B(["📦 build<br/>image → ACR :sha"]) --> S(["🚀 staging"]) --> FS{{"🛡️ fumée"}}
    FS -- "✔" --> EV{{"🛡️ evals<br/>si déclencheur"}} -- "✔ ou sautées" --> R(["🏷️ release<br/>tag vX.Y.Z"]) --> P(["🌐 production"]) --> FP{{"🛡️ fumée"}}
    T -- "✘" --> X(["⛔ chaîne arrêtée<br/>merge refusé"])
    P -. "make rollback (1 opération)" .-> RB(["↩️ image précédente"])
    classDef plat fill:#1E3A8A,stroke:#1E3A8A,color:#fff
    classDef ok fill:#DCFCE7,stroke:#15803D,color:#14532D
    classDef ko fill:#FEE2E2,stroke:#B91C1C,color:#7F1D1D
    classDef gate fill:#EDE9FE,stroke:#7C3AED,color:#3B0764
    class PR,M,P plat
    class L,B,S,R ok
    class X,RB ko
    class T,EP,FS,EV,FP gate
```

Un merge sur `main` relance `lint` et `test` avant `build`. Les evals (portes : réussite ≥ 80 % et latence
p95 ≤ 30 s) ne tournent que si le prompt, le golden dataset ou la version du LLM changent (voir *Évaluer l'agent*).

## Sprint 3 (v0.2.0) : vers trois projets

Le sprint 3 fait évoluer ce dépôt en **monorepo à trois projets**, livrés sur trois branches dans cet ordre :

| Projet | Langage | Rôle | État |
|---|---|---|---|
| [`gateway/`](gateway/README.md) | C# · YARP · .NET 10 | **Seule entrée publique** : routage pur vers les deux services | ✅ branche `feat/gateway` — construite et testée par la CI (job `gateway`), pas encore déployée |
| `rag/` | Python · hexagonal | Corpus Légifrance, ingestion, recherche hybride, agent cité | ⏳ branche `feat/rag` |
| `underwriting-admin/` | C# · Clean Architecture · .NET 10 | Dossiers (BOLA) et référentiel SQL des traces OpenTelemetry | ⏳ branche `feat/underwriting-admin` |

Le code ci-dessous (`agentinsurflow/`) est encore celui du sprint 2 ; il rejoindra `rag/` sur la branche `feat/rag`.

## Arborescence

```text
.
├── agentinsurflow/            # le code (architecture hexagonale légère)
│   ├── api.py                 #   adaptateur HTTP : /health, POST /api/agent, Swagger sur /
│   ├── agent.py               #   domaine : l'agent, ne connaît que le port ClientLLM
│   ├── llm.py                 #   port ClientLLM + FakeLLM (tests) + adaptateur AzureLLM + config
│   └── prompts/systeme.md     #   prompt système (le modifier déclenche les evals)
├── tests/
│   ├── unit/                  # agent, adaptateur LLM (HTTP simulé, sans réseau), evals
│   └── integration/           # requête HTTP → route → agent, LLM mocké
├── tools/evals.py             # make eval : golden set contre une API (locale, PR ou staging) + manifeste
├── .github/workflows/
│   ├── ci-cd.yml              # lint → test → [evals-pr] · build → staging → [evals] → production
│   └── deploy.yml             # déploiement + fumée ; lancé à la main = rollback
├── infra/
│   ├── bootstrap.sh           # make infra : crée l'infra Azure (idempotent)
│   └── protection-main.json   # make proteger : main exige lint, test et evals-pr verts
├── docs/                      # secrets, blocage, rollback, démo d'atelier
├── eval/
│   ├── golden.jsonl           # cas d'évaluation de l'agent (versionnés)
│   ├── preuves/               # journaux de chaîne, rapports d'evals et captures versionnés
│   └── ateliers/              # grille de l'atelier croisé n°2
├── llm.env                    # version du LLM épinglée (la modifier déclenche les evals)
├── Dockerfile · Makefile · pyproject.toml · uv.lock · .python-version
└── .env.example               # toutes les clés, sans valeurs
```

| Python | Équivalent .NET |
|---|---|
| `pyproject.toml` + `uv.lock` | `.csproj` + `packages.lock.json` |
| `uv sync --locked` | `dotnet restore --locked-mode` |
| FastAPI + `Depends` | Minimal API + injection de dépendances |
| `ClientLLM` (`Protocol`) | `interface ILlmClient` |
| `app.dependency_overrides` | remplacer un service dans `WebApplicationFactory` |
| `pydantic-settings` | `IOptions<T>` lié à la configuration |

## Lancer (en local)

Prérequis : [uv](https://docs.astral.sh/uv/) et Docker.

```bash
cp .env.example .env      # remplir AZURE_OPENAI_ENDPOINT (+ la clé, ou az login) ; sans endpoint : mode dégradé
make install              # dépendances figées par uv.lock
make run                  # http://localhost:8000 → Swagger
make docker               # la même chose, dans l'image qui part en production
```

Exemple de réponse de `POST /api/agent` : `{"texte": "…", "mode": "llm", "modele": "Kimi-K2.5"}`.
Avec `"mode": "degrade"`, le LLM n'est pas joignable (ou ne répond pas en 30 s, `LLM_DELAI_S`) et la demande
part en revue humaine (source : dossier-conception-v1.md, K5).

**Authentification au LLM** : **aucune clé hors de ton poste**. Le code utilise Entra ID
(`DefaultAzureCredential`) : OIDC dans la CI, identité managée dans Container Apps (rôle *Cognitive Services
User* sur `svespuce-971`). En local, la clé `AZURE_OPENAI_API_KEY` du `.env` reste possible, sinon `az login`.
Le modèle est épinglé dans `llm.env` ; l'endpoint est accepté avec ou sans le suffixe `/openai/v1`.

## Tester

```bash
make lint                 # ruff (style) + mypy (typage strict)
make test                 # pytest : unitaires + intégration, couverture ≥ 80 %
```

Les jobs `lint` et `test` **mockent toujours le LLM** (`FakeLLM`, HTTP simulé) : aucun secret ni appel réel.
Seules les **evals** et la **fumée** appellent le vrai modèle.
La couverture visée est la fourchette **80–83 %** ; la porte bloquante est sa borne basse (80 %, `pyproject.toml`).

## Évaluer l'agent (evals)

```bash
make eval                               # contre l'API locale (make run)
make eval URL=https://<staging>         # contre un environnement déployé
```

`tools/evals.py` rejoue `eval/golden.jsonl` en boîte noire (seul `POST /api/agent` est appelé). Chaque cas
passe des contrôles déterministes, et la latence est mesurée :

| Contrôle | Vérifie |
|---|---|
| `mode_llm` | Le LLM a vraiment répondu (pas de repli) |
| `non_vide` | La réponse n'est pas vide |
| `longueur` | La réponse est bornée (600 caractères par défaut), y compris sous injection |
| `contient_un` | La réponse contient au moins un mot attendu (sujet, réponse en français) |
| **latence p95** | ≤ 30 s (dossier-conception-v1.md, D11) |

Porte : taux de réussite ≥ **80 %** (seuil de départ, `🔴 à calibrer`) **et** latence p95 ≤ 30 s.

**Déclenchement** : les evals ne tournent que si un fichier susceptible de changer leur résultat a changé
**depuis le dernier manifeste validé** (tag `manifeste-X.Y.Z-build.N`, job `changements`) ; sinon elles sont
sautées et la chaîne continue. Un manifeste dont les evals ont échoué n'est jamais tagué : le commit suivant
le réévalue, même s'il ne touche pas ces fichiers. Sans aucun tag `manifeste-*`, les evals tournent.

| Déclencheur | Fichier versionné |
|---|---|
| Prompt | `agentinsurflow/prompts/` |
| Golden dataset | `eval/golden.jsonl` |
| Version du LLM | `llm.env` (`AZURE_OPENAI_DEPLOYMENT`, épinglé et copié dans l'image) |

| Job | Quand | Contre quoi | Authentification au LLM |
|---|---|---|---|
| `evals-pr` | PR (exigé avant merge) | API lancée **dans le runner** | **OIDC, sans clé** (rôle sur la ressource Foundry) |
| `evals` | merge, avant la production | **staging** déployé | celle de la Container App |

**Artefact de chaque passage** : `evals-pr-<sha>` ou `evals-staging-<sha>` (onglet *Summary* du run). Le rapport
JSON s'ouvre sur un **manifeste** qui dit ce qui a été évalué :

| Champ du manifeste | Contenu |
|---|---|
| `version` | Version du manifeste : `X.Y.Z-build.N` (pyproject + n° de run GitHub) |
| `date`, `commit`, `run`, `cible` | Quand, quel commit, lien du run GitHub, URL évaluée |
| `modele` | Déploiement épinglé (`llm.env`) **et** modèle observé dans les réponses de l'API |
| `prompts` | Chaque prompt : fichier, empreinte sha256, contenu |
| `golden` | Fichier, empreinte sha256, identifiants des cas |
| `portes` | Seuil de réussite et latence p95 maximale appliqués |

Viennent ensuite le taux, la latence p95 et le détail de chaque cas (contrôles ratés, latence, réponse).
Exemple réel : `eval/preuves/evals-local-2026-10-15.json`.

> 🔁 **Analogie .NET** : une suite xUnit de non-régression, sauf qu'on mesure un **taux de réussite** au lieu
> d'exiger 100 % de `Assert`, car la sortie d'un LLM n'est pas déterministe (source : dossier-conception-v1.md, §7.2).

## Déployer

Installation, à faire une seule fois :

1. `make infra` crée le groupe de ressources, l'ACR, l'environnement Container Apps et deux apps (staging,
   production), reprend l'application Entra `agentinsurflow` et ses 4 fédérations OIDC (`main`, `staging`,
   `production`, `pull_request`), puis attribue les rôles. Il affiche les valeurs à reporter. Attribuer des rôles
   exige *Owner* ou *User Access Administrator*.
2. Reporter à la main les variables et le secret dans GitHub en suivant [docs/secrets.md](docs/secrets.md).
3. `git push`, puis `make proteger` : `main` n'accepte plus que des commits dont `lint`, `test` et `evals-pr`
   sont verts (un `evals-pr` sauté compte comme vert).

Ensuite, chaque **merge sur `main`** déclenche toute la chaîne, sans action manuelle. Trois versions :

| Version | Forme | Désigne | Où la lire |
|---|---|---|---|
| Release | `vX.Y.Z` (ex. `v0.1.3`) | le commit livré en production, tagué juste avant | `/health` → `release`, tags Git, résumé du run |
| Image | SHA du commit | l'artefact déployé | `/health` → `version`, tag de l'image dans l'ACR |
| Manifeste | `X.Y.Z-build.N` (ex. `0.1.0-build.42`) | ce qui a été évalué : modèle, prompts, golden dataset | `/health` → `manifeste`, rapport d'évaluation, tag `manifeste-…` |

Les trois sont calculées par le job `changements` puis **gravées dans l'image** : un rollback restaure aussi
les versions affichées. X.Y se choisissent à la main dans `pyproject.toml` (`version`).

- **Release** : Z est calculé par `tools/version.py` d'après les tags (`v0.1.0`, puis `v0.1.1`…) ; passer le
  pyproject à `0.2.0` donne `v0.2.0`. En staging, `release` est la **candidate** : le tag n'est posé qu'après
  staging et evals, juste avant la production.
- **Manifeste** : si le modèle, un prompt ou le golden dataset a changé, nouvelle version `X.Y.Z-build.<n° du
  run>` (`X.Y.Z-local` hors CI), taguée `manifeste-…` quand les evals passent ; sinon, celle du dernier manifeste
  validé.

### Ressources Azure actuelles

| Ressource | Nom | État |
|---|---|---|
| Groupe de ressources | `svespuceRG` (`swedencentral`) | ✅ |
| Registre d'images | `acerolazacr` (`acerolazacr.azurecr.io`) | ✅ créé |
| Environnement Container Apps | `cae-insurflow` | ✅ créé |
| Container App staging | `insurflow-staging` → `https://insurflow-staging.redstone-0f3be5e1.swedencentral.azurecontainerapps.io` | ✅ déployée |
| Container App production | `insurflow-production` → `https://insurflow-production.redstone-0f3be5e1.swedencentral.azurecontainerapps.io` | ✅ déployée |
| Modèle | `Kimi-K2.5` sur la ressource Foundry `svespuce-971` | ✅ |
| Application Entra de la CI | `agentinsurflow` + 4 fédérations OIDC | ✅ |
| Rôles (Contributor, AcrPush, AcrPull, Cognitive Services User) | — | ✅ attribués |

## Rollback

```bash
make rollback             # production → image précédente, en une opération
make rollback ENV=staging TAG=<sha>   # ou une version précise
```

Détails et scénario de répétition : [docs/rollback.md](docs/rollback.md).

## Preuves et atelier

| Sujet | Où |
|---|---|
| Secrets hors dépôt, report dans GitHub | [docs/secrets.md](docs/secrets.md) |
| Commit volontairement cassé et bloqué | [docs/preuve-blocage.md](docs/preuve-blocage.md) |
| Rollback | [docs/rollback.md](docs/rollback.md) |
| Script de la démo (20 min) | [docs/demo-atelier.md](docs/demo-atelier.md) |
| Journaux versionnés | `eval/preuves/` (`make preuve RUN=<id> NOM=<nom>`) |
| Rapport d'évaluation (manifeste + résultats) | artefact `evals-staging-<sha>` ou `evals-pr-<sha>` du run, à copier dans `eval/preuves/` |
| Grille de l'atelier | [eval/ateliers/sprint-2-grille.md](eval/ateliers/sprint-2-grille.md) |

## Hors périmètre du socle

Le parcours V1 n'est pas dans ce socle : RAG, MCP, HITL, gateway, OCR en A2A. Il viendra aux sprints suivants
(source : dossier-conception-v1.md). Les sujets encore ouverts (découpage des agents, protocoles…) ne sont pas présumés.
