# Gateway YARP : cibles standard (SDK .NET 10 ; global.json à la racine du monorepo)
SLN := AgentInsurFlow.Gateway.slnx
IMAGE ?= agentinsurflow-gateway:local
VERSION := $(shell git rev-parse HEAD 2>/dev/null || echo dev)

.PHONY: build test lint fmt docker-build

build:
	dotnet build $(SLN)

test:               ## TI (forme diamant : proxy pur) + couverture de lignes >= 80 %
	dotnet test --solution $(SLN) --results-directory TestResults \
	  --coverlet --coverlet-include "[AgentInsurFlow.*]*" --coverlet-output-format cobertura \
	  --coverlet-threshold 80 --coverlet-threshold-type line

lint:               ## style et analyseurs (avertissements = erreurs, Directory.Build.props)
	dotnet format $(SLN) --verify-no-changes

fmt:
	dotnet format $(SLN)

docker-build:       ## contexte = racine du monorepo (global.json, Directory.Build.props)
	docker build -f Dockerfile --build-arg APP_VERSION=$(VERSION) -t $(IMAGE) ..
