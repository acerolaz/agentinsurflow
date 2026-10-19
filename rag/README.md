# 🐍 rag — AgentInsurFlow

Service Python (FastAPI) du **corpus réglementaire** : il portera l'ingestion des textes Légifrance (Code des assurances, périmètre auto), la recherche hybride (cosinus pgvector + plein texte + numéro d'article, fusion RRF) et l'**agent** à réponses citées, qui refuse hors corpus (spec du sprint 3, décision S3-16).

> **État (v0.4.0, Tasks R0 → R5)** : socle hexagonal ; PostgreSQL annexe et migrations de la base `vecteurs` ; domaine du corpus (nettoyage, dédup, découpage, porte) ; embeddings et jetons Entra ; **ingestion et recherche hybride en REST**. L'agent à 3 verrous (R6), la CLI Légifrance (R7) et le jeu de démo (R8) arrivent ensuite.

## API (REST, S3-24)

| Méthode · URI | Rôle d'app | Succès | Ressource |
|---|---|---|---|
| `POST /api/ingestions` | `Ingestion` | 201 + `Location` | Ingestion d'un lot d'articles (1 à 50) → rapport (lus, insérés, inchangés, nouvelles versions, rejets avec raison, quasi-doublons) |
| `GET /api/ingestions?limit&offset` | `Ingestion` | 200 | Rapports journalisés, du plus récent au plus ancien |
| `GET /api/ingestions/{ingestion_id}` | `Ingestion` | 200 · 404 | Un rapport (`INGESTION_INTROUVABLE`) |
| `GET /api/extraits?question=…&top_k=…` | `Gestionnaire` | 200 | Extraits qui passent la porte de pertinence ; sinon `statut = NOT_FOUND_IN_CORPUS`, `resultats = []` |
| `GET /api/documents/{doc_id}` | `Gestionnaire` | 200 · 404 | Traçabilité : versions et chunks d'un article, sans les vecteurs (`DOCUMENT_INTROUVABLE`) |
| `POST /api/reponses` | — (jeton exigé par la gateway ; vérifié par rag en R6) | 200 | Réponse de l'agent (calculée, non conservée) — remplace `POST /api/agent` du sprint 2 |
| `GET /health` | — | 200 | Santé et versions servies |

- **Erreurs** en ProblemDetails (RFC 9457) avec un `code` : 401 `JETON_ABSENT` / `JETON_INVALIDE`, 403 `ROLE_MANQUANT`, 404, 503 `EMBEDDINGS_INDISPONIBLES` / `BASE_INDISPONIBLE` / `AUTH_INDISPONIBLE` / `CONFIGURATION_INCOMPLETE` (`RAG_SEUIL` absent) ; 422 = validation (format FastAPI).
- **Refus par défaut** : chaque route du corpus exige son rôle ; les collections lisibles viennent du rôle (`Gestionnaire` → `textes_reglementaires`), aucune sinon.
- **Swagger** : derrière la gateway, le document est servi en `GET /rag/openapi.json` dans la **page Swagger unique** (`http://localhost:8000/`). Il ne déclare pas de `servers` : le « Try it out » appelle les routes publiques de la gateway (jeton, rôle et limite de débit). Sans gateway, rag sert aussi son propre Swagger sur `/` (`http://localhost:8001/` dans le compose).
- Un test de contrat vérifie que seules ces routes sont publiées (les anciens noms RPC répondent 404) et que chacune documente ses réponses d'erreur et son schéma de sécurité.
- Sans PostgreSQL, sans Entra ou sans `RAG_SEUIL` configurés, l'API **démarre quand même** ; les routes concernées répondent 503 (le déploiement actuel n'a pas encore la base annexe).

## Recherche hybride (spec §4.1)

1. **Référence exacte** : un numéro d'article cité (« L. 211-1 », « l211-1 ») est cherché directement et passe en tête.
2. **Deux classements fusionnés par RRF** (k = 60), dans une seule requête SQL : cosinus (index HNSW) et plein texte français (`websearch_to_tsquery`, `ts_rank_cd`, index GIN — ce n'est pas BM25, écart S3-11). Seules les versions non obsolètes des collections du rôle sont lues.
3. **Porte de pertinence** : la question passe si le cosinus max ≥ `RAG_SEUIL` (obligatoire, à calibrer) ou si elle cite exactement un article présent. Le score RRF ne sert qu'à ordonner.

## Base de données

rag ne connaît que la base **`vecteurs`**, avec deux comptes : `writer` (ingestion) et `reader` (recherche) — `infrastructure/postgres/connexions.py` (`ConfigBD`, `creer_moteurs`). Les bases `dossiers` et `traces` appartiennent à underwriting-admin. L'image annexe (`infra/postgres/`) crée les 3 bases, leurs versions `_test`, les 6 comptes, et l'extension `vector` dans `vecteurs` ; chaque compte n'a `CONNECT` que sur sa base. Les mots de passe viennent de l'environnement (`PG_*_PASSWORD`, `.env` en local, générés à chaque run en CI).

**Schéma** (Alembic, `rag/alembic.ini`, section `vecteurs`, migrations écrites à la main en SQL ; `make migrate`, compte `migrateur`) :

| Table | Rôle | Index |
|---|---|---|
| `document` | une **version** d'un article (`doc_id`, `version`, `etat`, `date_debut`, `url_source`, `hash_contenu`, `obsolete`) ; UNIQUE (`doc_id`, `version`), `collection` limitée à 4 valeurs | B-tree partiel (`collection`) WHERE NOT `obsolete` |
| `chunk` | unité de recherche et de citation (`article`, `texte`, `embedding vector(1536)`, `tsv` **généré** en français) | **HNSW** cosinus · **GIN** (`tsv`) · B-tree (`article`) |
| `ingestion` | rapports d'ingestion (`instantane_sha256`, `rapport` jsonb) | — |

Droits : `writer` → SELECT, INSERT, UPDATE (+ séquences) ; `reader` → SELECT seul (vérifié par un test).

## Architecture hexagonale

`~/.claude/rules/python-hexagonal.md` : le domaine ne dépend d'aucun framework ; la règle est **vérifiée par un test** (`tests/unit/test_architecture.py`).

```mermaid
flowchart LR
    API["api/<br/>FastAPI, DTO Pydantic"] --> APP["application/<br/>cas d'usage"]
    APP --> DOM["domain/<br/>entités, ports (Protocol)"]
    INFRA["infrastructure/<br/>Azure OpenAI…"] --> DOM
    API -. "câblage (Depends)" .-> INFRA
```

| Couche | Contenu | Analogie .NET |
|---|---|---|
| `domain/ports.py` | `ClientLLM` (`Protocol`), `ErreurLLM` | `interface ILlmClient` |
| `domain/models.py` | `Reponse` (dataclass) | entité du Domain |
| `application/use_cases/repondre.py` | l'agent : prompt système, mode dégradé | service applicatif |
| `infrastructure/azure_openai/` | `AzureLLM`, `fabrique_llm`, `ConfigLLM` | implémentation injectée par DI |
| `api/` | `app`, routes `sante` et `agent`, DTO `Question`, `ReponseDTO`, `Sante` | Minimal API + DTO |

```text
rag/
├── agentinsurflow_rag/{domain,application,infrastructure,api}/ · prompts/systeme.md
├── tests/unit/          TU : aucune I/O, ports simulés (fakes.py)
├── tests/integration/   TI : l'API en mémoire (TestClient), LLM simulé
├── pyproject.toml       paquet agentinsurflow-rag, dépendances d'exécution
├── Dockerfile           contexte = racine du monorepo (uv.lock commun)
└── llm.env              version du LLM épinglée (la modifier déclenche les evals)
```

## Commandes (depuis la racine du monorepo)

```bash
make install            # uv sync --locked (espace de travail : racine + rag)
make lint               # ruff + mypy strict
make test               # TU, sans Docker
make test-integration   # TU + TI (PostgreSQL du compose), couverture >= 80 %
make pyramide           # porte 70 / 20 / 10 (S3-22)
make up                 # postgres + rag (:8001) + gateway (:8000, Swagger unique)
make migrate            # schéma de la base vecteurs (Alembic, compte migrateur)
make run                # rag seul : http://localhost:8000 (lancé depuis rag/ : llm.env y est lu)
make build              # docker build -f rag/Dockerfile .
```

## Tests

| Niveau | Dossier | Exemples |
|---|---|---|
| TU | `tests/unit` | `test_corpus.py` (nettoyage, HTML, numéros, dédup, découpage, porte), `test_ingerer.py` et `test_rechercher.py` (cas d'usage, dépôt en mémoire `FakeDepotCorpus`), `test_jetons.py`, `test_embeddings.py`, `test_agent.py`, `test_llm.py` (HTTP simulé par `httpx.MockTransport`), `test_connexions.py`, `test_architecture.py` (règle de dépendance) |
| TI | `tests/integration` | `test_api.py` (requête HTTP → route → cas d'usage, LLM simulé ; contrat REST, document OpenAPI sans `servers`), `test_bd.py` (image annexe : 6 comptes, cloisonnement des bases, pgvector), `test_migrations_vecteurs.py` (tables, index, droits, unicité, `tsv`, downgrade/upgrade), `test_ingestions_api.py` et `test_extraits_api.py` (ressources REST contre PostgreSQL : SQL RRF réel, idempotence, versions, 503 sans écriture, rôles), `test_securite.py` |

⚠️ `test_llm.py` utilise `httpx.MockTransport` sans réseau ni socket : il reste en TU selon la règle de la pyramide (aucune I/O réelle).
