#!/usr/bin/env bash
# Inscriptions d'application Entra des API (A3) et attributions de rôles (A4) : G5, S3-20, S3-25.
# `make entra [DOMAINE=aibrokerflow.fr] [DEMO_USER_ID=<objet>]` (lit le .env). Idempotent. Lancé par Acerola.
# Prérequis : az login avec le droit de créer des inscriptions d'application dans le tenant.
# La gateway n'a pas d'inscription propre : elle valide les jetons des deux audiences.
# U5 : permission déléguée rag → underwriting (OBO, S3-20) et identité managée fédérée de rag (A7).
# #47 : chaque API pré-autorise ses clients OBO (preAuthorizedApplications) : aucun consentement
# administrateur, qui vaudrait pour tous les utilisateurs du tenant, n'est nécessaire.
# ⑥ (#15, T9 #64) : serveur MCP agentinsurflow-mcp, dans sa propre Container App, identité managée propre.
# ⑦ (#70) : rag dans sa propre Container App, identité managée propre uami-insurflow-rag-app (fédérée sur agentinsurflow-rag,
# rôle Telemetrie). L'identité partagée uami-insurflow-rag ne reste qu'à la Container App principale (gateway) : son nom
# est gardé (la Function de calcul et le rôle Foundry y sont rattachés) ; la renommer est une décision d'Acerola.
# Le rôle LLM de rag et l'accès Foundry relèvent de infra/llm.sh. Les inscriptions des agents (azp) relèvent de #7.
# Prérequis : `make infra` (Container Apps MCP et rag).
set -euo pipefail

for v in AZURE_RESOURCE_GROUP APP_STAGING APP_PRODUCTION MCP_APP_STAGING MCP_APP_PRODUCTION RAG_APP_STAGING RAG_APP_PRODUCTION AZURE_CLIENT_ID; do
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
MCP_SCOPE=5b8e1c72-6d4a-4e39-b0f1-2a7c9d3e4f03
MCP_GESTIONNAIRE=5b8e1c72-6d4a-4e39-b0f1-2a7c9d3e4f01

echo "① Redirections SPA de la page Swagger unique (S3-24)"
redirections=("http://localhost:8000/oauth2-redirect.html")
for app in "$APP_STAGING" "$APP_PRODUCTION"; do
  fqdn=$(az containerapp show -n "$app" -g "$AZURE_RESOURCE_GROUP" --query properties.configuration.ingress.fqdn -o tsv)
  redirections+=("https://$fqdn/oauth2-redirect.html")
done
[ -z "${DOMAINE:-}" ] || redirections+=("https://$DOMAINE/oauth2-redirect.html")
printf '   %s\n' "${redirections[@]}"
spa=$(printf '%s\n' "${redirections[@]}" | jq -R . | jq -s .)

# inscrire <nom> <id du scope> "<appId client>…" <rôle>=<id>… : crée l'inscription au besoin, puis impose
# l'URI d'API, le scope access_as_user, les rôles, les redirections et la pré-autorisation sur ce scope
# d'Azure CLI et des clients donnés (#47 : leur OBO se passe du consentement administrateur du tenant).
# Deux URI d'API : api://<nom> (jetons du poste et de l'E2E) et api://<appId>, que l'OBO de rag et du
# serveur MCP demande (sans elle : AADSTS500011, ressource introuvable).
inscrire() {
  local nom=$1 scope=$2 clients app_id objet corps
  clients=$(printf '%s\n' "$CLI" $3 | jq -R . | jq -s .)
  shift 3
  app_id=$(az ad app list --display-name "$nom" --query "[0].appId" -o tsv)
  [ -n "$app_id" ] || app_id=$(az ad app create --display-name "$nom" --sign-in-audience AzureADMyOrg --query appId -o tsv)
  objet=$(az ad app show --id "$app_id" --query id -o tsv)
  corps=$(jq -n --arg uri "api://$nom" --arg uri_id "api://$app_id" --arg scope "$scope" \
    --argjson clients "$clients" --argjson spa "$spa" \
    --arg texte "Appeler $nom au nom de l'utilisateur connecté" \
    --argjson roles "$(printf '%s\n' "$@" | jq -R 'split("=") | {value: .[0], id: .[1], displayName: .[0],
      description: .[0], allowedMemberTypes: ["User", "Application"], isEnabled: true}' | jq -s .)" '{
    identifierUris: [$uri, $uri_id], spa: {redirectUris: $spa}, appRoles: $roles,
    api: {requestedAccessTokenVersion: 2,
      oauth2PermissionScopes: [{id: $scope, value: "access_as_user", type: "User", isEnabled: true,
        adminConsentDisplayName: $texte, adminConsentDescription: $texte,
        userConsentDisplayName: $texte, userConsentDescription: $texte}],
      preAuthorizedApplications: [$clients[] | {appId: ., delegatedPermissionIds: [$scope]}]}}')
  # Deux passes : Graph refuse une pré-autorisation qui vise un scope pas encore créé
  az rest --method PATCH --uri "$GRAPH/applications/$objet" --headers content-type=application/json \
    --body "$(jq '.api.preAuthorizedApplications = []' <<<"$corps")" -o none
  az rest --method PATCH --uri "$GRAPH/applications/$objet" --headers content-type=application/json \
    --body "$corps" -o none
  az ad sp show --id "$app_id" -o none 2>/dev/null || az ad sp create --id "$app_id" -o none
  echo "$app_id"
}

echo "② Inscriptions agentinsurflow-mcp, agentinsurflow-rag et agentinsurflow-underwriting (A3)"
# Les clients OBO d'abord : une API ne pré-autorise qu'un appId déjà inscrit
mcp=$(inscrire agentinsurflow-mcp "$MCP_SCOPE" "" "Gestionnaire=$MCP_GESTIONNAIRE")
rag=$(inscrire agentinsurflow-rag "$RAG_SCOPE" "$mcp" "Gestionnaire=$RAG_GESTIONNAIRE" "Ingestion=$RAG_INGESTION")
uw=$(inscrire agentinsurflow-underwriting "$UW_SCOPE" "$rag $mcp" \
  "Gestionnaire=$UW_GESTIONNAIRE" "Telemetrie=$UW_TELEMETRIE")

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

echo "④ Permission déléguée rag → underwriting/access_as_user (OBO, pré-autorisée en ②)"
rag_objet=$(az ad app show --id "$rag" --query id -o tsv)
# remplace seulement l'entrée de l'API underwriting : relancer ne la duplique pas
acces=$(az ad app show --id "$rag" --query "requiredResourceAccess" -o json |
  jq -c --arg api "$uw" --arg scope "$UW_SCOPE" \
    'map(select(.resourceAppId != $api)) + [{resourceAppId: $api, resourceAccess: [{id: $scope, type: "Scope"}]}]')
az rest --method PATCH --uri "$GRAPH/applications/$rag_objet" --headers content-type=application/json \
  --body "{\"requiredResourceAccess\": $acces}" -o none

echo "⑤ Identité managée attribuée par l'utilisateur (A7) : rattachée aux Container Apps principales (gateway, underwriting-admin)"
UAMI=${UAMI:-uami-insurflow-rag} # même défaut dans infra/calcul.sh (identité de la gateway)
az identity show -n "$UAMI" -g "$AZURE_RESOURCE_GROUP" -o none 2>/dev/null ||
  az identity create -n "$UAMI" -g "$AZURE_RESOURCE_GROUP" -o none
uami_id=$(az identity show -n "$UAMI" -g "$AZURE_RESOURCE_GROUP" --query id -o tsv)
uami_client=$(az identity show -n "$UAMI" -g "$AZURE_RESOURCE_GROUP" --query clientId -o tsv)
for app in "$APP_STAGING" "$APP_PRODUCTION"; do
  # `assign` ajoute l'identité sans toucher à l'identité système (AcrPull) ; sans effet si déjà posée
  az containerapp identity assign -n "$app" -g "$AZURE_RESOURCE_GROUP" --user-assigned "$uami_id" -o none
done
# (la fédération sur agentinsurflow-rag n'est plus ici : rag a son identité propre, ⑦)

echo "⑥ Serveur MCP agentinsurflow-mcp (inscrit en ②) : rôles, permissions déléguées mcp → rag et underwriting, identité managée propre"
attribuer "$mcp" "$MCP_GESTIONNAIRE" "$moi" "toi → Gestionnaire (mcp)"
attribuer "$mcp" "$MCP_GESTIONNAIRE" "$ci" "CI → Gestionnaire (mcp)"
[ -z "${DEMO_USER_ID:-}" ] || attribuer "$mcp" "$MCP_GESTIONNAIRE" "$DEMO_USER_ID" "2e gestionnaire → Gestionnaire (mcp)"
mcp_objet=$(az ad app show --id "$mcp" --query id -o tsv)
# OBO du serveur : access_as_user de rag et d'underwriting ; remplace ces deux entrées, relancer ne les duplique pas
acces=$(az ad app show --id "$mcp" --query "requiredResourceAccess" -o json |
  jq -c --arg rag "$rag" --arg rs "$RAG_SCOPE" --arg uw "$uw" --arg us "$UW_SCOPE" \
    'map(select(.resourceAppId != $rag and .resourceAppId != $uw)) + [
      {resourceAppId: $rag, resourceAccess: [{id: $rs, type: "Scope"}]},
      {resourceAppId: $uw, resourceAccess: [{id: $us, type: "Scope"}]}]')
az rest --method PATCH --uri "$GRAPH/applications/$mcp_objet" --headers content-type=application/json \
  --body "{\"requiredResourceAccess\": $acces}" -o none
# le serveur MCP envoie ses traces à la gateway (/v1/traces) avec un jeton d'application : rôle Telemetrie
mcp_sp=$(az ad sp show --id "$mcp" --query id -o tsv)
attribuer "$uw" "$UW_TELEMETRIE" "$mcp_sp" "serveur MCP → Telemetrie (underwriting)"
# Identité managée PROPRE au serveur MCP (sa Container App à lui), distincte de celle de rag et de la gateway (⑤) :
# la Function de calcul n'accepte que celle de la gateway, et le jeton du MCP n'ouvre rien d'autre que ses rôles
UAMI_MCP=uami-insurflow-mcp
az identity show -n "$UAMI_MCP" -g "$AZURE_RESOURCE_GROUP" -o none 2>/dev/null ||
  az identity create -n "$UAMI_MCP" -g "$AZURE_RESOURCE_GROUP" -o none
uami_mcp_id=$(az identity show -n "$UAMI_MCP" -g "$AZURE_RESOURCE_GROUP" --query id -o tsv)
uami_mcp_client=$(az identity show -n "$UAMI_MCP" -g "$AZURE_RESOURCE_GROUP" --query clientId -o tsv)
uami_mcp_principal=$(az identity show -n "$UAMI_MCP" -g "$AZURE_RESOURCE_GROUP" --query principalId -o tsv)
for app in "$MCP_APP_STAGING" "$MCP_APP_PRODUCTION"; do
  az containerapp identity assign -n "$app" -g "$AZURE_RESOURCE_GROUP" --user-assigned "$uami_mcp_id" -o none
done
# Identifiant fédéré uami-mcp : remplace celui de l'identité partagée (migration d'avant T9), sans secret client
sujet_mcp=$(az ad app federated-credential list --id "$mcp" --query "[?name=='uami-mcp'].subject | [0]" -o tsv)
if [ "$sujet_mcp" != "$uami_mcp_principal" ]; then
  [ -z "$sujet_mcp" ] || az ad app federated-credential delete --id "$mcp" --federated-credential-id uami-mcp
  az ad app federated-credential create --id "$mcp" -o none --parameters "{
    \"name\": \"uami-mcp\", \"issuer\": \"https://login.microsoftonline.com/$(az account show --query tenantId -o tsv)/v2.0\",
    \"subject\": \"$uami_mcp_principal\", \"audiences\": [\"api://AzureADTokenExchange\"]}"
fi

echo "⑦ rag (sa Container App) : identité managée propre fédérée sur agentinsurflow-rag, rôle Telemetrie"
UAMI_RAG=uami-insurflow-rag-app
az identity show -n "$UAMI_RAG" -g "$AZURE_RESOURCE_GROUP" -o none 2>/dev/null ||
  az identity create -n "$UAMI_RAG" -g "$AZURE_RESOURCE_GROUP" -o none
uami_rag_id=$(az identity show -n "$UAMI_RAG" -g "$AZURE_RESOURCE_GROUP" --query id -o tsv)
uami_rag_client=$(az identity show -n "$UAMI_RAG" -g "$AZURE_RESOURCE_GROUP" --query clientId -o tsv)
uami_rag_principal=$(az identity show -n "$UAMI_RAG" -g "$AZURE_RESOURCE_GROUP" --query principalId -o tsv)
for app in "$RAG_APP_STAGING" "$RAG_APP_PRODUCTION"; do
  az containerapp identity assign -n "$app" -g "$AZURE_RESOURCE_GROUP" --user-assigned "$uami_rag_id" -o none
done
# Identifiant fédéré uami-rag : remplace celui de l'identité partagée (avant #70) : la gateway ne peut plus se faire passer pour rag
sujet_rag=$(az ad app federated-credential list --id "$rag" --query "[?name=='uami-rag'].subject | [0]" -o tsv)
if [ "$sujet_rag" != "$uami_rag_principal" ]; then
  [ -z "$sujet_rag" ] || az ad app federated-credential delete --id "$rag" --federated-credential-id uami-rag
  az ad app federated-credential create --id "$rag" -o none --parameters "{
    \"name\": \"uami-rag\", \"issuer\": \"https://login.microsoftonline.com/$(az account show --query tenantId -o tsv)/v2.0\",
    \"subject\": \"$uami_rag_principal\", \"audiences\": [\"api://AzureADTokenExchange\"]}"
fi
# rag envoie ses traces à la gateway (/v1/traces) avec un jeton d'application : rôle Telemetrie d'underwriting-admin
attribuer "$uw" "$UW_TELEMETRIE" "$(az ad sp show --id "$rag" --query id -o tsv)" "rag → Telemetrie (underwriting)"

echo "✔ Variables GitHub du repo à poser :"
echo "   RAG_API_CLIENT_ID=$rag"
echo "   UNDERWRITING_API_CLIENT_ID=$uw"
echo "   MCP_API_CLIENT_ID=$mcp"
echo "   AZURE_UAMI_CLIENT_ID=$uami_client   (gateway seule depuis #70 ; Easy Auth de la Function : make calcul)"
echo "   AZURE_UAMI_RAG_CLIENT_ID=$uami_rag_client   (rag seul)"
echo "   AZURE_UAMI_MCP_CLIENT_ID=$uami_mcp_client   (serveur MCP seul)"
