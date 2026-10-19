-include .env
export

ENV ?= production
TAG ?=
URL ?= http://localhost:8000
IMAGE ?= agentinsurflow:local
VERSION := $(shell git rev-parse HEAD 2>/dev/null || echo dev)

# Monorepo : rag (Python, espace de travail uv à la racine), gateway/ et, plus tard,
# underwriting-admin/ (C#, leurs propres Makefile, appelés par gateway-<cible>).
.PHONY: install fmt lint test test-integration pyramide migrate ingest extraire up down eval calibrer run build docker infra proteger rollback preuve

install:            ## dépendances figées par uv.lock (≈ dotnet restore --locked-mode)
	uv sync --locked

fmt:
	uv run ruff format .
	uv run ruff check --fix .

lint:               ## porte 1 : style + typage
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy rag/agentinsurflow_rag tools

test:               ## TU, sans Docker (rag/tests/unit + outillage de la racine)
	uv run pytest tests rag/tests/unit --no-cov

test-integration:   ## porte 2 : TU + TI (PostgreSQL du compose), couverture >= 80 %
	docker compose up -d --build --wait postgres
	uv run pytest

migrate:            ## migrations Alembic de la base vecteurs (compte migrateur, PG_* du .env)
	cd rag && uv run alembic -n vecteurs upgrade head

ingest:             ## make ingest [URL=<gateway>] [INSTANTANE=data/raw/…] : Légifrance ou rejeu → /api/ingestions
	uv run python -m agentinsurflow_rag.cli.ingest --url $(URL) $(if $(INSTANTANE),--instantane $(INSTANTANE))

extraire:           ## extraction Légifrance seule → data/raw/ (identifiants PISTE du .env, bac à sable)
	uv run python -m agentinsurflow_rag.cli.ingest --sans-envoi

up:                 ## la solution en local : postgres + rag (:8001) + gateway (:8000, Swagger unique)
	docker compose up -d --build --wait

down:               ## arrête la solution et vide la base annexe
	docker compose down -v

pyramide:           ## porte S3-22 : TU >= 65 %, TI <= 25 %, E2E <= 15 % (rag + underwriting-admin + e2e)
	uv run python tools/pyramide.py

gateway-%:          ## cibles de gateway/Makefile : make gateway-test, gateway-lint, gateway-docker-build
	$(MAKE) -C gateway $*

eval:               ## porte 3 : make eval [URL=…] — golden set + jeu de démo (jeton : EVALS_JETON)
	uv run python tools/evals.py --url $(URL) --questions eval/questions-demo.jsonl

calibrer:           ## make calibrer URL=… — cosinus max par question, intervalle pour RAG_SEUIL
	uv run python tools/evals.py --calibrer --url $(URL) --questions eval/questions-demo.jsonl

run:                ## http://localhost:8000
	cd rag && uv run uvicorn agentinsurflow_rag.api:app --reload --port 8000

build:              ## image locale de rag, version = commit courant (contexte = racine, uv.lock)
	docker build -f rag/Dockerfile --build-arg APP_VERSION=$(VERSION) -t $(IMAGE) .

docker: build       ## l'image telle qu'elle tournera en Azure
	docker run --rm --env-file .env -p 8000:8000 $(IMAGE)

infra:              ## une fois : Azure (RG, ACR, Container Apps, OIDC) + variables GitHub
	bash infra/bootstrap.sh

proteger:           ## après le 1er push : main exige lint + test verts
	gh api -X PUT repos/$(GITHUB_REPO)/branches/main/protection --input infra/protection-main.json

rollback:           ## une opération : make rollback [ENV=staging] [TAG=<sha>] ; sans TAG = version précédente
	gh workflow run deploy.yml -R $(GITHUB_REPO) -f environnement=$(ENV) -f tag=$(TAG)

preuve:             ## make preuve RUN=<id> NOM=blocage-2026-10-20 → journal versionné
	gh run view $(RUN) -R $(GITHUB_REPO) --log > eval/preuves/$(NOM).log
	gh run view $(RUN) -R $(GITHUB_REPO) > eval/preuves/$(NOM).resume.txt
