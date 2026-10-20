# underwriting-admin : cibles standard (SDK .NET 10 ; global.json à la racine du monorepo)
SLN := AgentInsurFlow.UnderwritingAdmin.slnx
IMAGE ?= agentinsurflow-underwriting-admin:local
VERSION := $(shell git rev-parse HEAD 2>/dev/null || echo dev)

.PHONY: build test lint fmt docker-build

build:
	dotnet build $(SLN)

test:               ## TU + TI, couverture de lignes >= 80 % (fusionnée sur tous les projets de test)
	rm -rf TestResults
	dotnet test --solution $(SLN) --results-directory TestResults \
	  --coverlet --coverlet-include "[AgentInsurFlow.*]*" --coverlet-exclude-by-attribute CompilerGeneratedAttribute \
	  --coverlet-exclude-by-file "**/Migrations/**" --coverlet-output-format cobertura
	python3 couverture.py TestResults 80

lint:               ## style et analyseurs (avertissements = erreurs, Directory.Build.props)
	dotnet format $(SLN) --verify-no-changes

fmt:
	dotnet format $(SLN)

docker-build:       ## contexte = racine du monorepo (global.json, Directory.Build.props)
	docker build -f Dockerfile --build-arg APP_VERSION=$(VERSION) -t $(IMAGE) ..
