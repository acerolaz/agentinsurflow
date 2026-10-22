#!/usr/bin/env bash
# Function de calcul (évaluer_risque, calculer_prime) : `make calcul` (lit le .env). Idempotent.
# Lancé À LA MAIN par Acerola, jamais par un agent ni par la CI. Prérequis : az login, `make entra`
# déjà passé (MCP_API_CLIENT_ID, identité managée uami-insurflow-rag), droit de créer des inscriptions d'application.
# Crée : compte de stockage, deux Function Apps Flex Consumption (staging, production), inscription
# Entra agentinsurflow-calcul (rôle d'application Calcul, attribué au serveur MCP : il l'envoie à la gateway),
# Easy Auth (jeton de l'identité managée de la GATEWAY seule : le MCP n'appelle jamais la Function ; /api/sante anonyme).
# Le code est déployé ensuite par .github/workflows/deploy.yml, pas ici.
set -euo pipefail

for v in AZURE_SUBSCRIPTION_ID AZURE_LOCATION AZURE_RESOURCE_GROUP AZURE_TENANT_ID MCP_API_CLIENT_ID \
  CALCUL_STORAGE CALCUL_APP_STAGING CALCUL_APP_PRODUCTION; do
  [ -n "${!v:-}" ] || { echo "✘ $v manquant dans .env"; exit 1; }
done
RG=$AZURE_RESOURCE_GROUP
GRAPH=https://graph.microsoft.com/v1.0
CALCUL_ROLE=9c4b2f10-3d5e-4a67-8b19-6e0f1a2b3c01 # rôle d'application Calcul : identifiant fixe, relancer ne le change pas
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
  --body "$(jq -n --arg uri "api://$app_id" --arg role "$CALCUL_ROLE" '{identifierUris: [$uri], api: {requestedAccessTokenVersion: 2},
    appRoles: [{id: $role, value: "Calcul", displayName: "Calcul", description: "Appeler la Function de calcul par la gateway",
      allowedMemberTypes: ["Application"], isEnabled: true}]}')" -o none
existe az ad sp show --id "$app_id" || az ad sp create --id "$app_id" -o none

echo "②b Rôle Calcul : attribué au principal de service du serveur MCP (jeton d'application, route calcul de la gateway)"
sp_calcul=$(az ad sp show --id "$app_id" --query id -o tsv)
sp_mcp=$(az ad sp show --id "$MCP_API_CLIENT_ID" --query id -o tsv)
if [ "$(az rest --uri "$GRAPH/servicePrincipals/$sp_calcul/appRoleAssignedTo" \
  --query "length(value[?principalId=='$sp_mcp' && appRoleId=='$CALCUL_ROLE'])" -o tsv)" = 0 ]; then
  az rest --method POST --uri "$GRAPH/servicePrincipals/$sp_calcul/appRoleAssignedTo" \
    --headers content-type=application/json -o none \
    --body "{\"principalId\":\"$sp_mcp\",\"resourceId\":\"$sp_calcul\",\"appRoleId\":\"$CALCUL_ROLE\"}"
fi

echo "③ Easy Auth : seule la gateway entre (son identité managée), /api/sante reste anonyme"
# identité managée partagée rag/gateway, créée par `make entra` ; son client id est l'appid du jeton qu'elle obtient
gateway_client=$(az identity show -n uami-insurflow-rag -g "$RG" --query clientId -o tsv)
[ -n "$gateway_client" ] || { echo "✘ identité uami-insurflow-rag absente : lancer make entra d'abord"; exit 1; }
auth=$(jq -n --arg client "$app_id" --arg tenant "$AZURE_TENANT_ID" --arg gateway "$gateway_client" '{properties: {
  platform: {enabled: true},
  globalValidation: {requireAuthentication: true, unauthenticatedClientAction: "Return401",
    excludedPaths: ["/api/sante"]},
  identityProviders: {azureActiveDirectory: {enabled: true,
    registration: {clientId: $client, openIdIssuer: ("https://login.microsoftonline.com/" + $tenant + "/v2.0")},
    validation: {allowedAudiences: [("api://" + $client), $client],
      defaultAuthorizationPolicy: {allowedApplications: [$gateway]}}}}}}')
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
                      CALCUL_API_CLIENT_ID=$app_id
  Env. production     CALCUL_APP_NAME=$CALCUL_APP_PRODUCTION
                      CALCUL_URL=https://$(hote "$CALCUL_APP_PRODUCTION")
                      CALCUL_AUDIENCE=api://$app_id
                      CALCUL_API_CLIENT_ID=$app_id
  Le code part avec le prochain déploiement (deploy.yml).
FIN
