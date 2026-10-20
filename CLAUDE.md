# AgentInsurFlow — contrat transverse du monorepo

Trois projets, chacun avec son README : [`gateway/`](gateway/README.md) (C#, YARP, seule entrée publique), [`rag/`](rag/README.md) (Python, hexagonal) et `underwriting-admin/` (C#, Clean Architecture, à venir).

## Architectures

- **Python → hexagonale** : `~/.claude/rules/python-hexagonal.md`. `domain/` et `application/` n'importent ni FastAPI, ni Pydantic, ni SQLAlchemy, ni OpenTelemetry, ni SDK : `rag/tests/unit/test_architecture.py` le vérifie.
- **C# → Clean Architecture** : `~/.claude/rules/csharp-clean-architecture.md`. La gateway n'a qu'un projet `Api` (proxy, pas de couche artificielle).
- **Tests** : `.claude/rules/testing-pyramid.md` (70 / 20 / 10, porte `make pyramide`).

## Non-négociables

- **Aucun secret** dans le dépôt ni dans GitHub : `.env.example` sans valeurs, `.env` jamais commité ; Azure en OIDC et identités managées.
- **Écritures Azure et Entra** (`az … create/update/set`) : rédigées dans `infra/*.sh`, lancées à la main par Acerola, jamais par un agent.
- **Seule la gateway est exposée** ; elle valide le jeton et le rôle par route, et **chaque service revalide** le jeton.
- **API REST** documentées en OpenAPI, consultables dans la page Swagger unique de la gateway ; erreurs en ProblemDetails avec un `code`.
- **Git** : une branche par projet (`feat/gateway` → `feat/rag` → `feat/underwriting-admin`), PR en brouillon ; jamais de push sur `main`, jamais de force-push.
- **Français** partout (code métier, tests, docs) ; vocabulaire « superviseur / orchestrateur ».

## Commandes (racine)

`make install` · `make lint` · `make test` (TU) · `make test-integration` (TU + TI, PostgreSQL du compose) · `make pyramide` · `make up` / `make down` (solution en local, Swagger unique sur `http://localhost:8000/`) · `make run` · `make build` · `make gateway-test` (et toute cible de `gateway/Makefile` en `gateway-<cible>`).

**Versions** (`pyproject.toml` racine et `rag/pyproject.toml`) : fixées par Acerola, jamais relevées d'office. R0 → 0.3.0, R1 → 0.4.0 ; **R2 → R8 restent en 0.4.0**.
