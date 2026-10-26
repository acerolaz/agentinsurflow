# AgentInsurFlow — contrat transverse du monorepo

Chaque projet a son README : [`gateway/`](gateway/README.md) (C#, YARP, seule entrée publique ; porte aussi `/api/llm` vers Foundry et `/api/calcul` vers la Function), [`rag/`](rag/README.md) (Python, hexagonal), [`serveur-mcp/`](serveur-mcp/README.md) (Python, outils MCP), [`fonction-calcul/`](fonction-calcul/README.md) (Azure Function Python : risque et prime), [`agentic-cluster/`](agentic-cluster/README.md) (Python, hexagonal, LangGraph : la Saga et les agents Pièces, Analyste, Rédacteur, Actuaire, revue humaine) et [`underwriting-admin/`](underwriting-admin/README.md) (C#, Clean Architecture : dossiers et référentiel des traces). En Azure, chacun (sauf la Function) a sa Container App, la gateway seule à entrée publique. Les tests E2E vivent dans [`e2e/`](e2e/README.md).

## Architectures

- **Python → hexagonale** : `~/.claude/rules/python-hexagonal.md`. `domain/` et `application/` n'importent ni FastAPI, ni Pydantic, ni SQLAlchemy, ni OpenTelemetry, ni SDK : `rag/tests/unit/test_architecture.py` le vérifie.
- **C# → Clean Architecture** : `~/.claude/rules/csharp-clean-architecture.md`. La gateway n'a qu'un projet `Api` (proxy, pas de couche artificielle).
- **Tests** : `.claude/rules/testing-pyramid.md` (70 / 20 / 10, porte `make pyramide`).

## Non-négociables

- **Aucun secret** dans le dépôt ni dans GitHub : `.env.example` sans valeurs, `.env` jamais commité ; Azure en OIDC et identités managées.
- **Écritures Azure et Entra** (`az … create/update/set`) : rédigées dans `infra/*.sh`, lancées à la main par Acerola, jamais par un agent.
- **Seule la gateway est exposée** ; elle valide le jeton et le rôle par route, et **chaque service revalide** le jeton.
- **API REST** documentées en OpenAPI, consultables dans la page Swagger unique de la gateway ; erreurs en ProblemDetails avec un `code`.
- **Git** : une branche par projet (`feat/gateway` → `feat/rag` → `feat/underwriting-admin` → `feat/mcp`), PR en brouillon. Pratique actuelle : une branche par sujet (`feat/…`, `fix/…`, `docs/…`, ex. `docs/maj-26-10`), une PR en brouillon par branche ; jamais de push sur `main`, jamais de force-push.
- **Français** partout (code métier, tests, docs) ; vocabulaire « superviseur / Saga » (la Saga : automate déterministe qui orchestre les agents du cluster et écrit l’état).

## Commandes (racine)

`make install` · `make lint` · `make test` (TU) · `make test-integration` (TU + TI, PostgreSQL du compose) · `make pyramide` · `make up` / `make down` (solution en local, Swagger unique sur `http://localhost:8000/`) · `make run` · `make build` · `make gateway-test` (et toute cible de `gateway/Makefile` en `gateway-<cible>`).

**Versions** (`pyproject.toml` racine et `rag/pyproject.toml`) : fixées par Acerola, jamais relevées d'office. R0 → 0.3.0, R1 → 0.4.0 (R2 → R8 restent en 0.4.0) ; **release v0.5.0** pour `feat/underwriting-admin` (racine seulement, `rag/pyproject.toml` reste en 0.4.0) ; **release v0.6.0** pour `feat/mcp` (racine seulement : serveur MCP, calcul, canal LLM, une Container App par service).
