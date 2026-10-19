# Gateway YARP — contexte de build = racine du monorepo : docker build -f gateway/Dockerfile .
FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY global.json Directory.Build.props ./
COPY gateway/src/AgentInsurFlow.Gateway.Api/AgentInsurFlow.Gateway.Api.csproj gateway/src/AgentInsurFlow.Gateway.Api/
RUN dotnet restore gateway/src/AgentInsurFlow.Gateway.Api/AgentInsurFlow.Gateway.Api.csproj
COPY gateway/src/ gateway/src/
RUN dotnet publish gateway/src/AgentInsurFlow.Gateway.Api -c Release -o /app --no-restore

FROM mcr.microsoft.com/dotnet/aspnet:10.0
WORKDIR /app
COPY --from=build /app .

# Versions servies par /health, gravées au build : SHA du commit, release vX.Y.Z
ARG APP_VERSION=dev APP_RELEASE=dev
ENV APP_VERSION=$APP_VERSION APP_RELEASE=$APP_RELEASE ASPNETCORE_HTTP_PORTS=8000

# Utilisateur non root fourni par l'image aspnet
USER app
EXPOSE 8000
ENTRYPOINT ["dotnet", "AgentInsurFlow.Gateway.Api.dll"]
