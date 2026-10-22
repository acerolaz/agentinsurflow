#!/usr/bin/env bash
# Function de calcul (évaluer_risque, calculer_prime) : `make calcul` (lit le .env). Idempotent.
# Lancé À LA MAIN par Acerola, jamais par un agent ni par la CI. Prérequis : az login, `make entra`
# déjà passé (MCP_API_CLIENT_ID), droit de créer des inscriptions d'application.
# Crée : compte de stockage, deux Function Apps Flex Consumption (staging, production), inscription
# Entra agentinsurflow-calcul, Easy Auth (jeton du serveur MCP seul ; /api/sante anonyme).
# Le code est déployé ensuite par .github/workflows/deploy.yml, pas ici.
set -euo pipefail

for v in AZURE_SUBSCRIPTION_ID AZURE_LOCATION AZURE_RESOURCE_GROUP AZURE_TENANT_ID MCP_API_CLIENT_ID \
  CALCUL_STORAGE CALCUL_APP_STAGING CALCUL_APP_PRODUCTION; do
  [ -n "${!v:-}" ] || { echo "✘ $v manquant dans .env"; exit 1; }
done
RG=$AZURE_RESOURCE_GROUP
GRAPH=https://graph.microsoft.com/v1.0
existe() { "$@" -o none 2>/dev/null; }

echo "① Compte de stockage et Function Apps (Flex Consumption, Python 3.12)"
az account set -s "$AZURE_SUBSCRIPTION_ID"
existe az storage account show -n "$CALCUL_STORAGE" -g "$RG" ||
  az storage account create -n "$CALCUL_STORAGE" -g "$RG" -l "$AZURE_LOCATION" --sku Standard_LRS \
    --allow-blob-public-access false -o none
for app in "$CALCUL_APP_STAGING" "$CALCUL_APP_PRODUCTION"; do
  existe az functionapp show -n "$app" -g "$RG" ||
    az functionapp create -n "$app" -g "$RG" --storage-account "$CALCUL_STORAGE" \
      --flexconsumption-location "$AZURE_LOCATION" --runtime python --runtime-version 3.12 -o none
done

echo "② Inscription Entra agentinsurflow-calcul"
nom=agentinsurflow-calcul
app_id=$(az ad app list --display-name "$nom" --query "[0].appId" -o tsv)
[ -n "$app_id" ] || app_id=$(az ad app create --display-name "$nom" --sign-in-audience AzureADMyOrg --query appId -o tsv)
objet=$(az ad app show --id "$app_id" --query id -o tsv)
# api://<appId> : l'audience que demande le serveur MCP (CALCUL_AUDIENCE) ; jetons v2
az rest --method PATCH --uri "$GRAPH/applications/$objet" --headers content-type=application/json \
  --body "$(jq -n --arg uri "api://$app_id" '{identifierUris: [$uri], api: {requestedAccessTokenVersion: 2}}')" -o none
existe az ad sp show --id "$app_id" || az ad sp create --id "$app_id" -o none

echo "③ Easy Auth : seul le serveur MCP entre, /api/sante reste anonyme"
auth=$(jq -n --arg client "$app_id" --arg tenant "$AZURE_TENANT_ID" --arg mcp "$MCP_API_CLIENT_ID" '{properties: {
  platform: {enabled: true},
  globalValidation: {requireAuthentication: true, unauthenticatedClientAction: "Return401",
    excludedPaths: ["/api/sante"]},
  identityProviders: {azureActiveDirectory: {enabled: true,
    registration: {clientId: $client, openIdIssuer: ("https://login.microsoftonline.com/" + $tenant + "/v2.0")},
    validation: {allowedAudiences: [("api://" + $client)],
      defaultAuthorizationPolicy: {allowedApplications: [$mcp]}}}}}}')
for app in "$CALCUL_APP_STAGING" "$CALCUL_APP_PRODUCTION"; do
  id=$(az functionapp show -n "$app" -g "$RG" --query id -o tsv)
  az rest --method put --uri "https://management.azure.com$id/config/authsettingsV2?api-version=2022-03-01" \
    --body "$auth" -o none
done

hote() { az functionapp show -n "$1" -g "$RG" --query defaultHostName -o tsv; }
cat <<FIN

✔ Function de calcul prête. À reporter À LA MAIN dans GitHub (procédure : docs/secrets.md) :
  Env. staging        CALCUL_APP_NAME=$CALCUL_APP_STAGING
                      CALCUL_URL=https://$(hote "$CALCUL_APP_STAGING")
                      CALCUL_AUDIENCE=api://$app_id
  Env. production     CALCUL_APP_NAME=$CALCUL_APP_PRODUCTION
                      CALCUL_URL=https://$(hote "$CALCUL_APP_PRODUCTION")
                      CALCUL_AUDIENCE=api://$app_id
  Le code part avec le prochain déploiement (deploy.yml).
FIN
