#!/usr/bin/env bash
# Canal LLM par la gateway (#70) : `make llm` (lit le .env). Idempotent.
# Lancé À LA MAIN par Acerola, jamais par un agent ni par la CI. Prérequis : az login, `make entra` déjà passé
# (inscription agentinsurflow-rag, identité managée uami-insurflow-rag), droit de créer des inscriptions d'application
# ET d'attribuer/retirer des rôles Azure sur la ressource Foundry (Owner ou User Access Administrator).
# Fait : inscription Entra agentinsurflow-llm (audience de la route /api/llm, rôle d'application LLM attribué à rag) ;
# inscription agentinsurflow-gateway-local (secret client pour le .env, affiché une seule fois) ; Foundry sans clé
# (disableLocalAuth) ; rôle « Cognitive Services OpenAI User » réservé à l'identité managée de la gateway et à
# agentinsurflow-gateway-local, RETIRÉ de toute autre identité. Les rôles hérités d'un niveau supérieur et les
# propriétaires de la ressource échappent à ce script (limite de gouvernance, docs/secrets.md §4).
set -euo pipefail

for v in AZURE_SUBSCRIPTION_ID AZURE_RESOURCE_GROUP FOUNDRY_NAME FOUNDRY_RESOURCE_GROUP; do
  [ -n "${!v:-}" ] || { echo "✘ $v manquant dans .env"; exit 1; }
done
RG=$AZURE_RESOURCE_GROUP
GRAPH=https://graph.microsoft.com/v1.0
LLM_ROLE=4d7a1b20-5e3c-4f68-9a1d-7c0e2b3d4f01 # rôle d'application LLM : identifiant fixe, relancer ne le change pas
ROLE_FOUNDRY="Cognitive Services OpenAI User"
UAMI=${UAMI:-uami-insurflow-rag} # même défaut que infra/entra.sh ⑤ et infra/calcul.sh : identité managée de la gateway
existe() { "$@" -o none 2>/dev/null; }
az account set -s "$AZURE_SUBSCRIPTION_ID"

# inscrire <nom> : crée l'inscription au besoin et son principal de service ; affiche l'appId
inscrire() {
  local id
  id=$(az ad app list --display-name "$1" --query "[0].appId" -o tsv)
  [ -n "$id" ] || id=$(az ad app create --display-name "$1" --sign-in-audience AzureADMyOrg --query appId -o tsv)
  existe az ad sp show --id "$id" || az ad sp create --id "$id" -o none
  echo "$id"
}

echo "① Inscription Entra agentinsurflow-llm : audience de la route /api/llm, rôle d'application LLM"
llm=$(inscrire agentinsurflow-llm)
objet=$(az ad app show --id "$llm" --query id -o tsv)
# api://<appId> : l'audience que demande rag (LLM_AUDIENCE) ; jetons v2 (aud = GUID, d'où la 2e audience de la gateway)
az rest --method PATCH --uri "$GRAPH/applications/$objet" --headers content-type=application/json \
  --body "$(jq -n --arg uri "api://$llm" --arg role "$LLM_ROLE" '{identifierUris: [$uri], api: {requestedAccessTokenVersion: 2},
    appRoles: [{id: $role, value: "LLM", displayName: "LLM", description: "Appeler le modèle par la gateway",
      allowedMemberTypes: ["Application"], isEnabled: true}]}')" -o none

echo "②  Rôle LLM : attribué au principal de service de rag (jeton d'application, route llm de la gateway)"
sp_llm=$(az ad sp show --id "$llm" --query id -o tsv)
rag=$(az ad app list --display-name agentinsurflow-rag --query "[0].appId" -o tsv)
[ -n "$rag" ] || { echo "✘ agentinsurflow-rag absente : lancer make entra d'abord"; exit 1; }
sp_rag=$(az ad sp show --id "$rag" --query id -o tsv)
if [ "$(az rest --uri "$GRAPH/servicePrincipals/$sp_llm/appRoleAssignedTo" \
  --query "length(value[?principalId=='$sp_rag' && appRoleId=='$LLM_ROLE'])" -o tsv)" = 0 ]; then
  az rest --method POST --uri "$GRAPH/servicePrincipals/$sp_llm/appRoleAssignedTo" \
    --headers content-type=application/json -o none \
    --body "{\"principalId\":\"$sp_rag\",\"resourceId\":\"$sp_llm\",\"appRoleId\":\"$LLM_ROLE\"}"
fi
# (les agents de #7 recevront ce même rôle quand ils seront inscrits)

echo "③  Inscription agentinsurflow-gateway-local : identité de la gateway en local (secret client dans le .env)"
gw_local=$(inscrire agentinsurflow-gateway-local)
sp_gw_local=$(az ad sp show --id "$gw_local" --query id -o tsv)
secret=""
if [ "$(az ad app credential list --id "$gw_local" --query "length([?displayName=='gateway-local'])" -o tsv)" = 0 ]; then
  # affiché une seule fois, à reporter dans le .env : jamais dans GitHub, jamais dans le dépôt
  secret=$(az ad app credential reset --id "$gw_local" --append --display-name gateway-local --years 1 --query password -o tsv)
fi

echo "④  Foundry $FOUNDRY_NAME : plus aucune clé (disableLocalAuth)"
foundry=$(az cognitiveservices account show -n "$FOUNDRY_NAME" -g "$FOUNDRY_RESOURCE_GROUP" --query id -o tsv)
az resource update --ids "$foundry" --set properties.disableLocalAuth=true -o none

echo "⑤  Rôle « $ROLE_FOUNDRY » : gateway et gateway-local seulement"
gw_principal=$(az identity show -n "$UAMI" -g "$RG" --query principalId -o tsv)
[ -n "$gw_principal" ] || { echo "✘ identité $UAMI absente : lancer make entra d'abord"; exit 1; }
attribuer_foundry() { # principal, type, libellé
  [ -n "$(az role assignment list --assignee "$1" --role "$ROLE_FOUNDRY" --scope "$foundry" --query '[0].id' -o tsv)" ] ||
    az role assignment create --assignee-object-id "$1" --assignee-principal-type "$2" --role "$ROLE_FOUNDRY" \
      --scope "$foundry" -o none
  echo "   ✔ $3"
}
attribuer_foundry "$gw_principal" ServicePrincipal "gateway ($UAMI)"
attribuer_foundry "$sp_gw_local" ServicePrincipal "agentinsurflow-gateway-local"
# Toute autre attribution de ce rôle, posée sur la ressource elle-même, est retirée (Container Apps, CI, comptes humains)
retirees=0
while IFS=$'\t' read -r id principal; do
  [ -n "$id" ] || continue
  [ "$principal" != "$gw_principal" ] && [ "$principal" != "$sp_gw_local" ] || continue
  az role assignment delete --ids "$id" -o none
  echo "   ✘ retiré : $principal"
  retirees=$((retirees + 1))
done < <(az role assignment list --scope "$foundry" --role "$ROLE_FOUNDRY" \
  --query "[?scope=='$foundry'].[id, principalId]" -o tsv)
echo "   $retirees attribution(s) retirée(s)"
echo "   Autres rôles sur la ressource (à vérifier à la main : un rôle de données autre que OpenAI User ouvre aussi le modèle) :"
az role assignment list --scope "$foundry" --query "[?roleDefinitionName!='$ROLE_FOUNDRY'].{role:roleDefinitionName, principal:principalName, scope:scope}" -o table

endpoint=$(az cognitiveservices account show -n "$FOUNDRY_NAME" -g "$FOUNDRY_RESOURCE_GROUP" \
  --query "properties.endpoints.\"OpenAI Language Model Instance API\"" -o tsv 2>/dev/null || true)
[ -n "$endpoint" ] || endpoint=$(az cognitiveservices account show -n "$FOUNDRY_NAME" -g "$FOUNDRY_RESOURCE_GROUP" --query properties.endpoint -o tsv)
cat <<FIN

✔ Canal LLM prêt. À reporter À LA MAIN (procédure : docs/secrets.md) :
  Variables du repo   LLM_AUDIENCE=api://$llm
                      LLM_API_CLIENT_ID=$llm
                      FOUNDRY_ENDPOINT=${endpoint%/}
                      AZURE_OPENAI_ENDPOINT=https://<FQDN de la gateway>/api/llm   (evals-pr désactivé ; deploy.yml le calcule)
  .env local          LLM_AUDIENCE=api://$llm
                      LLM_API_CLIENT_ID=$llm
                      FOUNDRY_ENDPOINT=${endpoint%/}
                      GATEWAY_CLIENT_ID=$gw_local
FIN
if [ -n "$secret" ]; then
  echo "                      GATEWAY_CLIENT_SECRET=$secret   🔒 affiché UNE SEULE FOIS, .env seulement"
else
  echo "  (secret de agentinsurflow-gateway-local déjà créé : le .env le garde ; pour en refaire un, supprimer 'gateway-local' dans Entra puis relancer)"
fi
