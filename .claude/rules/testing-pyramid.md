# Pyramide de tests — AgentInsurFlow

*Reprise de la règle `testing-pyramid` de Sorabel (niveaux, critères, outillage), **plus** les proportions décidées au sprint 3 (S3-22) et leur porte.*

**Portée** : `rag` (Python), `underwriting-admin` (C#) et `e2e/`. La **gateway** est comptée à part (forme diamant, voir plus bas).

## Les niveaux et leur part

| Niveau | Part visée | Critère d'appartenance | Python (`rag`) | C# (`underwriting-admin`) | Cible |
|---|---|---|---|---|---|
| **TU** — unitaire | **70 %** | Aucune I/O, aucun framework, aucun conteneur. Domaine et cas d'usage, **ports simulés** seulement. Millisecondes. | `rag/tests/unit` (`pytest`, `tests/fakes.py`) | `*.Domain.Tests`, `*.Application.Tests` (xUnit) | `make test` |
| **TI** — intégration | **20 %** | Un adapter face à sa vraie dépendance ou à un double fidèle (PostgreSQL du compose, `httpx.MockTransport`, WireMock.Net), **ou** l'API complète en mémoire (contrat HTTP : routes, codes, ProblemDetails). | `rag/tests/integration` (`TestClient`, `httpx.AsyncClient`) | `*.Infrastructure.Tests`, `*.Api.Tests` (`WebApplicationFactory`) | `make test`, `make test-integration` |
| **E2E** | **10 %** | La solution qui tourne (compose ou staging), **via la gateway**, avec ses vraies dépendances. Lent, exclu du cycle rapide. | `e2e/` (pytest, `E2E_URL`) | — | `make test-e2e URL=…` |

- **Porte** : `make pyramide` (`tools/pyramide.py`) compte les tests de chaque niveau et **échoue si TU < 65 %, TI > 25 %, E2E > 15 %, ou si un niveau est vide**. Elle tourne en CI (job `pyramide`) mais reste **informative** (`continue-on-error`, décision d'Acerola) tant que les seuils ne sont pas atteints (≈ 52 % TU / 46 % TI / 2 % E2E au 20/10) ; elle deviendra bloquante après une tâche dédiée aux TU.
- **Couverture ≥ 80 %** de lignes, par projet, mesurée sur TU + TI. Aucun quota par niveau.

### TU ou TI ?

Un test qui touche un socket, un fichier, une base ou une horloge système **n'est pas unitaire**, quel que soit le nom de son dossier. Un TU ne simule que des **ports** (`domain/ports.py`, interfaces C# du Domain ou de l'Application), jamais un détail d'infrastructure. Exception assumée : un adaptateur HTTP testé avec `httpx.MockTransport` (en mémoire, sans socket) reste un TU.

### TI ou E2E ?

Le TI démarre l'application **en mémoire**, backends doublés : il ne prouve rien du packaging ni de la configuration réelle. L'E2E démarre la solution **telle qu'elle est déployée**. Un changement qui touche le packaging, la configuration ou le démarrage n'est pas terminé sur la foi des seuls TU et TI.

## La gateway : forme « diamant »

Proxy (routes, politiques d'autorisation et limites de débit déclaratives) : presque aucune logique isolable. Ses tests sont des **TI** (`WebApplicationFactory` devant WireMock.Net), comptés à part. Écrire des TU sur sa configuration pour gonfler un compteur est un anti-pattern.

## Ce que Claude doit faire

- Avant d'écrire un test, nommer **son niveau** et vérifier qu'il en respecte le critère.
- Quand un niveau manque, le signaler plutôt que de compenser en gonflant un autre.
- Ne jamais écrire de test dont la seule fonction est d'augmenter la couverture ou un pourcentage.
- Viser la répartition par des **TU de domaine** (traitement du corpus, porte de pertinence, verrous, BOLA), pas par des TI supplémentaires.
