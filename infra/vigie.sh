#!/usr/bin/env bash
# Vigie (#54) : Application Insights par environnement, branché sur les 5 Container Apps et la Function.
# `make vigie ENV=staging|production` (lit le .env via le Makefile). Idempotent.
# Lancé À LA MAIN par Acerola, jamais par un agent ni la CI : écritures Azure.
# La chaîne de connexion ne s'affiche jamais (ni `set -x`, ni echo).
set -euo pipefail

# ⓪ ENV contrôlé avant toute lecture du .env
env=${1:-}
case "$env" in
  staging | production) ;;
  *) echo "✘ usage : bash infra/vigie.sh staging|production"; exit 1 ;;
esac
suffixe=$(printf '%s' "$env" | tr '[:lower:]' '[:upper:]')

for v in AZURE_RESOURCE_GROUP AZURE_LOCATION LOG_ANALYTICS_WORKSPACE \
  "APP_$suffixe" "CLUSTER_APP_$suffixe" "RAG_APP_$suffixe" "MCP_APP_$suffixe" "UW_APP_$suffixe" "CALCUL_APP_$suffixe"; do
  [ -n "${!v:-}" ] || { echo "✘ $v manquant dans .env"; exit 1; }
done
RG=$AZURE_RESOURCE_GROUP
appi="appi-insurflow-$env"
existe() { "$@" -o none 2>/dev/null; }

echo "① Composant Application Insights $appi (espace $LOG_ANALYTICS_WORKSPACE)"
az extension add -n application-insights -y -o none
if ! existe az monitor app-insights component show -a "$appi" -g "$RG"; then
  espace=$(az monitor log-analytics workspace show -n "$LOG_ANALYTICS_WORKSPACE" -g "$RG" --query id -o tsv)
  az monitor app-insights component create -a "$appi" -g "$RG" -l "$AZURE_LOCATION" \
    --workspace "$espace" --kind web --application-type web -o none
fi

echo "② Secret appinsights-connection sur les 5 Container Apps"
chaine=$(az monitor app-insights component show -a "$appi" -g "$RG" --query connectionString -o tsv)
for var in "APP_$suffixe" "CLUSTER_APP_$suffixe" "RAG_APP_$suffixe" "MCP_APP_$suffixe" "UW_APP_$suffixe"; do
  az containerapp secret set -n "${!var}" -g "$RG" -o none --secrets "appinsights-connection=$chaine"
done

echo "③ Function de calcul : APPLICATIONINSIGHTS_CONNECTION_STRING"
calcul="CALCUL_APP_$suffixe"
az functionapp config appsettings set -n "${!calcul}" -g "$RG" -o none \
  --settings "APPLICATIONINSIGHTS_CONNECTION_STRING=$chaine"

echo "④ ✔ $appi branché sur les 5 apps et la Function ($env). Chaîne de connexion non affichée."
echo "   Les anciens composants acerolaz-calcul-$env sont conservés (à retirer à la main une fois la vigie validée)."
echo "   Le prochain déploiement exige le secret appinsights-connection sur chaque app."
