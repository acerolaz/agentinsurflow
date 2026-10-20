#!/usr/bin/env bash
# Inscriptions d'application Entra des API (A3) et attributions de rôles (A4) : G5, S3-20, S3-25.
# `make entra [DOMAINE=aibrokerflow.fr] [DEMO_USER_ID=<objet>]` (lit le .env). Idempotent. Lancé par Acerola.
# Prérequis : az login avec le droit de créer des inscriptions d'application dans le tenant.
# La gateway n'a pas d'inscription propre : elle valide les jetons des deux audiences.
# U5 ajoutera la permission déléguée rag → underwriting (OBO) et l'identité managée fédérée.
set -euo pipefail

for v in AZURE_RESOURCE_GROUP APP_STAGING APP_PRODUCTION AZURE_CLIENT_ID; do
  [ -n "${!v:-}" ] || { echo "✘ $v manquant dans .env"; exit 1; }
done
GRAPH=https://graph.microsoft.com/v1.0
CLI=04b07795-8ddb-461a-bbee-02f9e1bf7b46 # Azure CLI pré-autorisée : jetons de la CI et du poste
# Identifiants fixes des rôles et des scopes : relancer le script ne les change pas
RAG_SCOPE=3f6c2a1e-8b4d-4c7a-9e21-5d0b7a6f1c03
RAG_GESTIONNAIRE=3f6c2a1e-8b4d-4c7a-9e21-5d0b7a6f1c01
RAG_INGESTION=3f6c2a1e-8b4d-4c7a-9e21-5d0b7a6f1c02
UW_SCOPE=7a1d9e40-2c3b-4f58-8a6e-1b9c0d2e3f03
UW_GESTIONNAIRE=7a1d9e40-2c3b-4f58-8a6e-1b9c0d2e3f01
UW_TELEMETRIE=7a1d9e40-2c3b-4f58-8a6e-1b9c0d2e3f02

echo "① Redirections SPA de la page Swagger unique (S3-24)"
redirections=("http://localhost:8000/oauth2-redirect.html")
for app in "$APP_STAGING" "$APP_PRODUCTION"; do
  fqdn=$(az containerapp show -n "$app" -g "$AZURE_RESOURCE_GROUP" --query properties.configuration.ingress.fqdn -o tsv)
  redirections+=("https://$fqdn/oauth2-redirect.html")
done
[ -z "${DOMAINE:-}" ] || redirections+=("https://$DOMAINE/oauth2-redirect.html")
printf '   %s\n' "${redirections[@]}"
spa=$(printf '%s\n' "${redirections[@]}" | jq -R . | jq -s .)

# inscrire <nom> <id du scope> <rôle>=<id>… : crée l'inscription au besoin, puis impose
# l'URI d'API, le scope access_as_user, les rôles, les redirections et la pré-autorisation d'Azure CLI.
inscrire() {
  local nom=$1 scope=$2 app_id objet corps
  shift 2
  app_id=$(az ad app list --display-name "$nom" --query "[0].appId" -o tsv)
  [ -n "$app_id" ] || app_id=$(az ad app create --display-name "$nom" --sign-in-audience AzureADMyOrg --query appId -o tsv)
  objet=$(az ad app show --id "$app_id" --query id -o tsv)
  corps=$(jq -n --arg uri "api://$nom" --arg scope "$scope" --arg cli "$CLI" --argjson spa "$spa" \
    --arg texte "Appeler $nom au nom de l'utilisateur connecté" \
    --argjson roles "$(printf '%s\n' "$@" | jq -R 'split("=") | {value: .[0], id: .[1], displayName: .[0],
      description: .[0], allowedMemberTypes: ["User", "Application"], isEnabled: true}' | jq -s .)" '{
    identifierUris: [$uri], spa: {redirectUris: $spa}, appRoles: $roles,
    api: {requestedAccessTokenVersion: 2,
      oauth2PermissionScopes: [{id: $scope, value: "access_as_user", type: "User", isEnabled: true,
        adminConsentDisplayName: $texte, adminConsentDescription: $texte,
        userConsentDisplayName: $texte, userConsentDescription: $texte}],
      preAuthorizedApplications: [{appId: $cli, delegatedPermissionIds: [$scope]}]}}')
  # Deux passes : Graph refuse une pré-autorisation qui vise un scope pas encore créé
  az rest --method PATCH --uri "$GRAPH/applications/$objet" --headers content-type=application/json \
    --body "$(jq '.api.preAuthorizedApplications = []' <<<"$corps")" -o none
  az rest --method PATCH --uri "$GRAPH/applications/$objet" --headers content-type=application/json \
    --body "$corps" -o none
  az ad sp show --id "$app_id" -o none 2>/dev/null || az ad sp create --id "$app_id" -o none
  echo "$app_id"
}

echo "② Inscriptions agentinsurflow-rag et agentinsurflow-underwriting (A3)"
rag=$(inscrire agentinsurflow-rag "$RAG_SCOPE" "Gestionnaire=$RAG_GESTIONNAIRE" "Ingestion=$RAG_INGESTION")
uw=$(inscrire agentinsurflow-underwriting "$UW_SCOPE" "Gestionnaire=$UW_GESTIONNAIRE" "Telemetrie=$UW_TELEMETRIE")

# attribuer <appId de l'API> <id du rôle> <objet du principal> <libellé> : seulement s'il manque
attribuer() {
  local sp
  sp=$(az ad sp show --id "$1" --query id -o tsv)
  if [ "$(az rest --uri "$GRAPH/servicePrincipals/$sp/appRoleAssignedTo" \
    --query "length(value[?principalId=='$3' && appRoleId=='$2'])" -o tsv)" = 0 ]; then
    az rest --method POST --uri "$GRAPH/servicePrincipals/$sp/appRoleAssignedTo" \
      --headers content-type=application/json -o none \
      --body "{\"principalId\":\"$3\",\"resourceId\":\"$sp\",\"appRoleId\":\"$2\"}" ||
      echo "⚠ $4 : refusé (A5, consentement administrateur ?) ; repli : evals et E2E depuis le poste"
  fi
}

echo "③ Attributions des rôles (A4)"
moi=$(az ad signed-in-user show --query id -o tsv)
ci=$(az ad sp show --id "$AZURE_CLIENT_ID" --query id -o tsv)
attribuer "$rag" "$RAG_GESTIONNAIRE" "$moi" "toi → Gestionnaire (rag)"
attribuer "$rag" "$RAG_INGESTION" "$moi" "toi → Ingestion (rag)"
attribuer "$uw" "$UW_GESTIONNAIRE" "$moi" "toi → Gestionnaire (underwriting)"
attribuer "$uw" "$UW_TELEMETRIE" "$moi" "toi → Telemetrie (underwriting)"
attribuer "$rag" "$RAG_GESTIONNAIRE" "$ci" "CI → Gestionnaire (rag)"
attribuer "$rag" "$RAG_INGESTION" "$ci" "CI → Ingestion (rag)"
attribuer "$uw" "$UW_GESTIONNAIRE" "$ci" "CI → Gestionnaire (underwriting)"
attribuer "$uw" "$UW_TELEMETRIE" "$ci" "CI → Telemetrie (underwriting)"
if [ -n "${DEMO_USER_ID:-}" ]; then
  attribuer "$rag" "$RAG_GESTIONNAIRE" "$DEMO_USER_ID" "2e gestionnaire → Gestionnaire (rag)"
  attribuer "$uw" "$UW_GESTIONNAIRE" "$DEMO_USER_ID" "2e gestionnaire → Gestionnaire (underwriting)"
else
  echo "   (2e gestionnaire de démo : relancer avec DEMO_USER_ID=<id d'objet Entra>)"
fi

echo "✔ Variables GitHub du repo à poser :"
echo "   RAG_API_CLIENT_ID=$rag"
echo "   UNDERWRITING_API_CLIENT_ID=$uw"
