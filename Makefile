-include .env
export

ENV ?= production
TAG ?=
URL ?= http://localhost:8000
IMAGE ?= agentinsurflow:local
VERSION := $(shell git rev-parse HEAD 2>/dev/null || echo dev)

# Monorepo : rag (Python, espace de travail uv à la racine), gateway/ et underwriting-admin/
# (C#, leurs propres Makefile, appelés par gateway-<cible> et underwriting-<cible>).
.PHONY: garde-fous install fmt lint test test-integration test-e2e pyramide openapi migrate ingest extraire up down eval calibrer run build docker infra proteger rollback preuve

install:            ## dépendances figées par uv.lock (≈ dotnet restore --locked-mode)
	uv sync --locked

fmt:
	uv run ruff format .
	uv run ruff check --fix .

lint:               ## porte 1 : style + typage
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy rag/agentinsurflow_rag serveur-mcp/agentinsurflow_mcp fonction-calcul/agentinsurflow_calcul fonction-calcul/function_app.py agentic-cluster/agentinsurflow_cluster tools
	uv export --package agentinsurflow-calcul --no-emit-workspace --no-dev --no-hashes | diff - fonction-calcul/requirements.txt

test:               ## TU, sans Docker (rag + serveur-mcp, tests/unit + outillage de la racine)
	uv run pytest tests rag/tests/unit serveur-mcp/tests/unit fonction-calcul/tests/unit agentic-cluster/tests/unit --no-cov

test-integration:   ## porte 2 : TU + TI (PostgreSQL du compose), couverture >= 80 %
	docker compose up -d --build --wait postgres
	uv run pytest

test-e2e:           ## make test-e2e URL=<gateway> : la solution qui tourne (compose ou staging), jetons via az
	E2E_URL=$(URL) uv run pytest e2e --no-cov -rs

migrate:            ## migrations Alembic de la base vecteurs (compte migrateur, PG_* du .env)
	cd rag && uv run alembic -n vecteurs upgrade head

ingest:             ## make ingest [URL=<gateway>] [INSTANTANE=data/raw/…] : Légifrance ou rejeu → /api/ingestions
	uv run python -m agentinsurflow_rag.cli.ingest --url $(URL) $(if $(INSTANTANE),--instantane $(INSTANTANE))

extraire:           ## extraction Légifrance seule → data/raw/ (identifiants PISTE du .env, bac à sable)
	uv run python -m agentinsurflow_rag.cli.ingest --sans-envoi

up:                 ## la solution en local : postgres + rag (:8001) + underwriting-admin (:8002) + gateway (:8000, Swagger unique)
	docker compose up -d --build --wait

down:               ## arrête la solution et vide la base annexe
	docker compose down -v

pyramide:           ## porte S3-22 : TU >= 65 %, TI <= 25 %, E2E <= 15 % (rag + underwriting-admin + e2e)
	uv run python tools/pyramide.py

openapi:            ## docs/openapi/{rag,underwriting-admin}.json, générés depuis le code (sans démarrer la solution)
	uv run python -c "import json; from agentinsurflow_rag.api import app; \
	  open('docs/openapi/rag.json', 'w').write(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + '\n')"
	ASPNETCORE_ENVIRONMENT=Development env -u VERSION dotnet build underwriting-admin/src/AgentInsurFlow.UnderwritingAdmin.Api -p:OpenApiGenerateDocuments=true -v q # VERSION (SHA) serait lu comme la propriété MSBuild Version ; Development : pas de mot de passe PostgreSQL exigé

gateway-%:          ## cibles de gateway/Makefile : make gateway-test, gateway-lint, gateway-docker-build
	env -u VERSION $(MAKE) -C gateway $*  # VERSION (SHA git) serait lu comme la propriété MSBuild Version : restauration NuGet en échec (MSB4181)

underwriting-%:     ## cibles de underwriting-admin/Makefile : make underwriting-test, underwriting-lint
	env -u VERSION $(MAKE) -C underwriting-admin $*  # comme gateway-% : VERSION serait lu comme la propriété MSBuild Version

eval:               ## porte 3 : make eval [URL=…] — golden set + jeu de démo (jeton : EVALS_JETON)
	uv run python tools/evals.py --url $(URL) --questions eval/questions-demo.jsonl

calibrer:           ## make calibrer URL=… — cosinus max par question, intervalle pour RAG_SEUIL
	uv run python tools/evals.py --calibrer --url $(URL) --questions eval/questions-demo.jsonl

garde-fous:         ## taux de blocage par catégorie et faux positifs (modèles LLM Guard, lent)
	uv run python tools/garde_fous.py

run:                ## http://localhost:8000
	cd rag && uv run uvicorn agentinsurflow_rag.api:app --reload --port 8000

build:              ## image locale de rag, version = commit courant (contexte = racine, uv.lock)
	docker build -f rag/Dockerfile --build-arg APP_VERSION=$(VERSION) -t $(IMAGE) .

docker: build       ## l'image telle qu'elle tournera en Azure
	docker run --rm --env-file .env -p 8000:8000 $(IMAGE)

infra:              ## une fois : Azure (RG, ACR, Container Apps, OIDC) + variables GitHub
	bash infra/bootstrap.sh

domaine:            ## G4 : lie DOMAINE=… à la Container App de production (certificat managé)
	bash infra/domaine.sh "$(DOMAINE)"

entra:              ## G5 : inscriptions Entra des API + rôles [DOMAINE=…] [DEMO_USER_ID=…]
	bash infra/entra.sh

calcul:             ## Function de calcul : stockage, Function Apps, Entra, Easy Auth
	bash infra/calcul.sh

llm:                ## canal LLM (#70) : Entra llm + gateway-local, Foundry sans clé, rôle réservé à la gateway
	bash infra/llm.sh

annexe:             ## G5 : image PostgreSQL annexe + secrets des Container Apps
	bash infra/postgres-annexe.sh

proteger:           ## après le 1er push : main exige lint + test verts
	gh api -X PUT repos/$(GITHUB_REPO)/branches/main/protection --input infra/protection-main.json

rollback:           ## une opération : make rollback [ENV=staging] [TAG=<sha>] ; sans TAG = version précédente
	gh workflow run deploy.yml -R $(GITHUB_REPO) -f environnement=$(ENV) -f tag=$(TAG)

preuve:             ## make preuve RUN=<id> NOM=blocage-2026-10-20 → journal versionné
	gh run view $(RUN) -R $(GITHUB_REPO) --log > eval/preuves/$(NOM).log
	gh run view $(RUN) -R $(GITHUB_REPO) > eval/preuves/$(NOM).resume.txt
