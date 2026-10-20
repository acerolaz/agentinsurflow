# underwriting-admin — contexte de build = racine du monorepo : docker build -f underwriting-admin/Dockerfile .
FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
# protoc du paquet Debian : le protoc livré par Grpc.Tools (linux_arm64) plante (code 139) dans Docker Desktop sur Mac ARM
RUN apt-get update && apt-get install -y --no-install-recommends protobuf-compiler && rm -rf /var/lib/apt/lists/*
ENV PROTOBUF_PROTOC=/usr/bin/protoc
COPY global.json Directory.Build.props ./
COPY underwriting-admin/src/ underwriting-admin/src/
RUN dotnet restore underwriting-admin/src/AgentInsurFlow.UnderwritingAdmin.Api/AgentInsurFlow.UnderwritingAdmin.Api.csproj
RUN dotnet publish underwriting-admin/src/AgentInsurFlow.UnderwritingAdmin.Api -c Release -o /app --no-restore

FROM mcr.microsoft.com/dotnet/aspnet:10.0
WORKDIR /app
COPY --from=build /app .

# Versions servies par /health, gravées au build : SHA du commit, release vX.Y.Z
ARG APP_VERSION=dev APP_RELEASE=dev
ENV APP_VERSION=$APP_VERSION APP_RELEASE=$APP_RELEASE ASPNETCORE_HTTP_PORTS=8002

# Utilisateur non root fourni par l'image aspnet
USER app
EXPOSE 8002
ENTRYPOINT ["dotnet", "AgentInsurFlow.UnderwritingAdmin.Api.dll"]
