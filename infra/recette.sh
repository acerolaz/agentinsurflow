#!/usr/bin/env bash
# Recette K1 → K11 depuis l'espace gestionnaire : `make recette ACTION=…` (lit le .env).
# Lancé À LA MAIN par Acerola, jamais par un agent ni par la CI. Prérequis : az login.
#   redemarrer : redémarre la révision active du cluster (K11 : dossier en pause, puis « Reprendre »)
#   llm-off    : INSURFLOW_LLM_ACTIF=false sur le cluster (K5 : « Service temporairement indisponible »)
#   llm-on     : INSURFLOW_LLM_ACTIF=true (le prochain déploiement le remet aussi, infra/containerapp-cluster.yaml)
# Cible : CLUSTER_APP_NAME (défaut : ai-cluster-staging, jamais la production par défaut).
set -euo pipefail

[ -n "${AZURE_RESOURCE_GROUP:-}" ] || { echo "✘ AZURE_RESOURCE_GROUP manquant dans .env"; exit 1; }
RG=$AZURE_RESOURCE_GROUP
APP=${CLUSTER_APP_NAME:-ai-cluster-staging}

# `az containerapp update` rend la main dès la révision créée : l'ancienne sert encore les évaluations
# (recette du 27/10 : 000002 évalué LLM actif après llm-off). On attend la nouvelle, prête et à 100 %.
attendre_revision() {
  local rev etat=""
  rev=$(az containerapp show -n "$APP" -g "$RG" --query properties.latestRevisionName -o tsv)
  for _ in $(seq 60); do
    etat=$(az containerapp revision show -n "$APP" -g "$RG" --revision "$rev" \
      --query "[properties.runningState, properties.healthState, properties.trafficWeight]" -o tsv | tr '\n' ' ')
    case "$etat" in
      *Fail* | *Unhealthy*) echo "✘ $rev : $etat"; exit 1 ;; # avant le succès : « Unhealthy » contient « Healthy »
      Running*Healthy\ 100*) echo "✔ $rev prête, 100 % du trafic : lancer l'évaluation"; return ;;
    esac
    sleep 5
  done
  echo "✘ $rev pas prête après 5 min ($etat) : ne pas lancer l'évaluation"; exit 1
}

case "${1:-}" in
  redemarrer)
    rev=$(az containerapp show -n "$APP" -g "$RG" --query properties.latestRevisionName -o tsv)
    az containerapp revision restart -n "$APP" -g "$RG" --revision "$rev" -o none
    echo "✔ $rev redémarrée" ;;
  llm-off | llm-on)
    [ "$1" = llm-off ] && actif=false || actif=true
    az containerapp update -n "$APP" -g "$RG" --set-env-vars "INSURFLOW_LLM_ACTIF=$actif" -o none
    echo "… $APP : INSURFLOW_LLM_ACTIF=$actif, nouvelle révision en cours d'activation"
    attendre_revision ;;
  *) echo "usage : make recette ACTION=redemarrer|llm-off|llm-on [CLUSTER_APP_NAME=…]"; exit 1 ;;
esac
