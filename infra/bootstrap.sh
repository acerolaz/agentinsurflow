#!/usr/bin/env bash
# Reconstruit tout l'environnement depuis le repo : `make infra` (lit le .env via le Makefile).
# Idempotent : chaque ressource est d'abord cherchée, créée seulement si elle manque.
# Prérequis : az login (Owner ou Contributor + User Access Administrator sur la souscription), gh (lecture),
# et Docker. Ne touche pas à GitHub : les valeurs à reporter sont affichées à la fin.
# ponytail: CLI az au sprint 2 ; Terraform au sprint 3 (choix validé au Temps 1)
set -euo pipefail

for v in AZURE_SUBSCRIPTION_ID AZURE_LOCATION AZURE_RESOURCE_GROUP ACR_NAME CONTAINERAPPS_ENV \
  APP_STAGING APP_PRODUCTION GITHUB_REPO; do
  [ -n "${!v:-}" ] || { echo "✘ $v manquant dans .env"; exit 1; }
done
RG=$AZURE_RESOURCE_GROUP
existe() { "$@" -o none 2>/dev/null; }

echo "① Socle Azure"
az account set -s "$AZURE_SUBSCRIPTION_ID"
az extension add -n containerapp --upgrade -y -o none
# Un Reader ne peut pas enregistrer de fournisseur : on vérifie seulement
for ns in Microsoft.App Microsoft.OperationalInsights Microsoft.ContainerRegistry; do
  etat=$(az provider show -n "$ns" --query registrationState -o tsv)
  if [ "$etat" != "Registered" ]; then
    echo "✘ $ns : $etat. À demander au formateur : az provider register -n $ns"
    exit 1
  fi
done
az group create -n "$RG" -l "$AZURE_LOCATION" -o none
existe az acr show -n "$ACR_NAME" || az acr create -n "$ACR_NAME" -g "$RG" --sku Basic -o none
existe az containerapp env show -n "$CONTAINERAPPS_ENV" -g "$RG" ||
  az containerapp env create -n "$CONTAINERAPPS_ENV" -g "$RG" -l "$AZURE_LOCATION" -o none

echo "② Image d'amorçage + deux Container Apps (staging, production)"
amorce="$ACR_NAME.azurecr.io/agentinsurflow:amorce"
az acr login -n "$ACR_NAME"
docker build --platform linux/amd64 --build-arg APP_VERSION=amorce -t "$amorce" .
docker push "$amorce"
for app in "$APP_STAGING" "$APP_PRODUCTION"; do
  # identité managée « system » : tire les images de l'ACR sans mot de passe (AcrPull)
  existe az containerapp show -n "$app" -g "$RG" ||
    az containerapp create -n "$app" -g "$RG" --environment "$CONTAINERAPPS_ENV" \
      --image "$amorce" --registry-server "$ACR_NAME.azurecr.io" --registry-identity system \
      --ingress external --target-port 8000 --min-replicas 0 --max-replicas 1 -o none
done

echo "③ Identité de la CI : application Entra + fédération OIDC (aucun secret)"
nom_ci="$(basename "$GITHUB_REPO")"   # application Entra « agentinsurflow », déjà créée et fédérée
app_id=$(az ad app list --display-name "$nom_ci" --query "[0].appId" -o tsv)
[ -n "$app_id" ] || app_id=$(az ad app create --display-name "$nom_ci" --query appId -o tsv)
existe az ad sp show --id "$app_id" || az ad sp create --id "$app_id" -o none
# Préfixe du sujet OIDC tel que GitHub l'émet : format immuable (owner@id/repo@id) ou classique
prefixe=$(gh api "repos/$GITHUB_REPO/actions/oidc/customization/sub" --jq '.sub_claim_prefix // empty')
[ -n "$prefixe" ] || prefixe="repo:$GITHUB_REPO"
for sujet in ref:refs/heads/main environment:staging environment:production; do
  nom=$(echo "$sujet" | tr ':/' '--')
  existe az ad app federated-credential show --id "$app_id" --federated-credential-id "$nom" ||
    az ad app federated-credential create --id "$app_id" -o none --parameters "{
      \"name\": \"$nom\", \"issuer\": \"https://token.actions.githubusercontent.com\",
      \"subject\": \"$prefixe:$sujet\", \"audiences\": [\"api://AzureADTokenExchange\"]}"
done
attribuer() { # rôle, portée
  [ -n "$(az role assignment list --assignee "$app_id" --role "$1" --scope "$2" --query '[0].id' -o tsv)" ] ||
    az role assignment create --assignee "$app_id" --role "$1" --scope "$2" -o none
}
attribuer Contributor "$(az group show -n "$RG" --query id -o tsv)"
attribuer AcrPush "$(az acr show -n "$ACR_NAME" --query id -o tsv)"

cat <<FIN

✔ Infra prête. À reporter À LA MAIN dans GitHub (procédure : docs/secrets.md) :
  Variables du repo   AZURE_CLIENT_ID=$app_id
                      AZURE_TENANT_ID=$(az account show --query tenantId -o tsv)
                      AZURE_SUBSCRIPTION_ID=$AZURE_SUBSCRIPTION_ID
                      AZURE_RESOURCE_GROUP=$RG
                      ACR_NAME=$ACR_NAME
  Env. staging        CONTAINER_APP_NAME=$APP_STAGING
  Env. production     CONTAINER_APP_NAME=$APP_PRODUCTION
FIN
