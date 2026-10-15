-include .env
export

ENV ?= production
TAG ?=
URL ?= http://localhost:8000
IMAGE ?= agentinsurflow:local
VERSION := $(shell git rev-parse HEAD 2>/dev/null || echo dev)

.PHONY: install fmt lint test eval run build docker infra proteger rollback preuve

install:            ## dépendances figées par uv.lock (≈ dotnet restore --locked-mode)
	uv sync --locked

fmt:
	uv run ruff format .
	uv run ruff check --fix .

lint:               ## porte 1 : style + typage
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy agentinsurflow tools

test:               ## porte 2 : unitaires + intégration, couverture >= 80 %
	uv run pytest

eval:               ## porte 3 : make eval [URL=https://<staging>] — golden set contre l'API
	uv run python tools/evals.py --url $(URL)

run:                ## http://localhost:8000
	uv run uvicorn agentinsurflow.api:app --reload --port 8000

build:              ## image locale, version = commit courant
	docker build --build-arg APP_VERSION=$(VERSION) -t $(IMAGE) .

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
