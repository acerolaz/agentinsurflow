#!/usr/bin/env bash
# Vigie (#54) : Application Insights par environnement, branché sur les 5 Container Apps et la Function,
# puis Action Group e-mail, règles d'alerte AL-1 → AL-10 (infra/vigie/alertes.tsv) test de disponibilité et tableau de bord (S2).
# `make vigie ENV=staging|production` (lit le .env via le Makefile). Idempotent : tout est un PUT ARM.
# Lancé À LA MAIN par Acerola, jamais par un agent ni la CI : écritures Azure.
# ALERTE_EMAIL est exigé dès le départ, y compris pour les seules étapes App Insights (S1).
# La chaîne de connexion ne s'affiche jamais (ni `set -x`, ni echo).
# SC2016 : les marqueurs $APPI_ID… des .kql sont littéraux, substitués sans envsubst (absent du Mac).
# shellcheck disable=SC2016
set -euo pipefail

# `AZ` permet aux tests de substituer un faux az (tests/unit/faux_az.sh).
az() { command "${AZ:-az}" "$@"; }

# ⓪ ENV contrôlé avant toute lecture du .env
env=${1:-}
case "$env" in
  staging | production) ;;
  *) echo "✘ usage : bash infra/vigie.sh staging|production"; exit 1 ;;
esac
suffixe=$(printf '%s' "$env" | tr '[:lower:]' '[:upper:]')

for v in AZURE_RESOURCE_GROUP AZURE_LOCATION LOG_ANALYTICS_WORKSPACE ALERTE_EMAIL \
  "APP_$suffixe" "CLUSTER_APP_$suffixe" "RAG_APP_$suffixe" "MCP_APP_$suffixe" "UW_APP_$suffixe" "CALCUL_APP_$suffixe"; do
  [ -n "${!v:-}" ] || { echo "✘ $v manquant dans .env"; exit 1; }
done
RG=$AZURE_RESOURCE_GROUP
appi="appi-insurflow-$env"
existe() { "$@" -o none 2>/dev/null; }
dossier=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/vigie

echo "① Composant Application Insights $appi (espace $LOG_ANALYTICS_WORKSPACE)"
az extension add -n application-insights -y -o none
WORKSPACE_ID=$(az monitor log-analytics workspace show -n "$LOG_ANALYTICS_WORKSPACE" -g "$RG" --query id -o tsv)
if ! existe az monitor app-insights component show -a "$appi" -g "$RG"; then
  az monitor app-insights component create -a "$appi" -g "$RG" -l "$AZURE_LOCATION" \
    --workspace "$WORKSPACE_ID" --kind web --application-type web -o none
fi
APPI_ID=$(az monitor app-insights component show -a "$appi" -g "$RG" --query id -o tsv)

echo "② Secret appinsights-connection sur les 5 Container Apps"
chaine=$(az monitor app-insights component show -a "$appi" -g "$RG" --query connectionString -o tsv)
[ -n "$chaine" ] || { echo "✘ chaîne de connexion vide pour $appi"; exit 1; }
for var in "APP_$suffixe" "CLUSTER_APP_$suffixe" "RAG_APP_$suffixe" "MCP_APP_$suffixe" "UW_APP_$suffixe"; do
  az containerapp secret set -n "${!var}" -g "$RG" -o none --secrets "appinsights-connection=$chaine"
done

echo "③ Function de calcul : APPLICATIONINSIGHTS_CONNECTION_STRING"
calcul="CALCUL_APP_$suffixe"
az functionapp config appsettings set -n "${!calcul}" -g "$RG" -o none \
  --settings "APPLICATIONINSIGHTS_CONNECTION_STRING=$chaine"

echo "④ Action Group ag-insurflow-$env (e-mail)"
AG_ID=$(az monitor action-group create -n "ag-insurflow-$env" -g "$RG" --short-name insurflow \
  --action email vigie "$ALERTE_EMAIL" --query id -o tsv)

echo "⑤ Règles d'alerte AL-1 → AL-10"
CLUSTER_APP_VAR="CLUSTER_APP_$suffixe"
CLUSTER_APP=${!CLUSTER_APP_VAR}
# PRIX_USD_MILLION="m=entrée/sortie;…" → lignes datatable `"m",entrée,sortie,` (vide si non posé)
PRIX_KQL=""
if [ -n "${PRIX_USD_MILLION:-}" ]; then
  IFS=';' read -r -a prix <<<"$PRIX_USD_MILLION"
  for p in "${prix[@]}"; do
    p=${p//[[:space:]]/}
    [ -n "$p" ] || continue
    tarif=${p#*=}
    PRIX_KQL="$PRIX_KQL\"${p%%=*}\",${tarif%%/*},${tarif#*/},"
  done
fi
while IFS=$'\t' read -r id kql frequence fenetre operateur seuil gravite ancre; do
  if [ "$id" = AL-6 ] && [ -z "$PRIX_KQL" ]; then
    echo "   AL-6 non créée : PRIX_USD_MILLION absent du .env"
    continue
  fi
  case "$seuil" in
    env:*)
      nom_seuil=${seuil#env:}
      seuil=${!nom_seuil:-}
      if [ -z "$seuil" ]; then
        echo "   $id non créée : $nom_seuil absent du .env (seuil non décidé)"
        continue
      fi
      ;;
  esac
  q=$(<"$dossier/kql/$kql")
  q=${q//'$APPI_ID'/$APPI_ID}
  q=${q//'$CLUSTER_APP'/$CLUSTER_APP}
  q=${q//'$PRIX_KQL'/$PRIX_KQL}
  signal=$(head -n 1 "$dossier/kql/$kql")
  signal=${signal#*: }
  az monitor scheduled-query create -n "al-${id#AL-}-$env" -g "$RG" --scopes "$WORKSPACE_ID" \
    --condition "max 'valeur' from 'Q' $operateur $seuil" --condition-query "Q=$q" \
    --evaluation-frequency "$frequence" --window-size "$fenetre" --severity "$gravite" \
    --action-groups "$AG_ID" --auto-mitigate true -o none \
    --description "$id ($env) : $signal — https://github.com/acerolaz/agentinsurflow/blob/main/docs/exploitation.md#$ancre"
  echo "   $id créée (al-${id#AL-}-$env)"
done < <(tail -n +2 "$dossier/alertes.tsv")

echo "⑥ Test de disponibilité web-sante-$env"
gateway="APP_$suffixe"
GATEWAY_FQDN=$(az containerapp show -n "${!gateway}" -g "$RG" \
  --query properties.configuration.ingress.fqdn -o tsv)
az monitor app-insights web-test create -n "web-sante-$env" -g "$RG" -l "$AZURE_LOCATION" \
  --web-test-kind standard --defined-web-test-name "web-sante-$env" --synthetic-monitor-id "web-sante-$env" \
  --request-url "https://$GATEWAY_FQDN/health" --http-verb GET --expected-status-code 200 \
  --frequency 300 --timeout 30 --enabled true \
  --locations Id=emea-fr-pra-edge --locations Id=emea-nl-ams-azr --locations Id=emea-gb-db3-azr \
  --tags "hidden-link:$APPI_ID=Resource" -o none

echo "⑦ Tableau de bord vigie-$env"
az extension add -n portal -y -o none
# Modèle : chaque "@kql:<fichier>" devient le texte du .kql (identifiants substitués), puis $WORKSPACE_ID, $ENV, $LOCATION.
tableau=$(mktemp "${TMPDIR:-/tmp}/vigie-tableau.XXXXXX")
trap 'rm -f "$tableau" "$tableau.new"' EXIT
cp "$dossier/dashboard.json" "$tableau"
for ref in $(jq -r '.. | strings | select(startswith("@kql:"))' "$tableau" | sort -u); do
  q=$(<"$dossier/kql/${ref#@kql:}")
  q=${q//'$APPI_ID'/$APPI_ID}
  q=${q//'$CLUSTER_APP'/$CLUSTER_APP}
  q=${q//'$PRIX_KQL'/$PRIX_KQL}
  jq --arg ref "$ref" --arg q "$q" 'walk(if . == $ref then $q else . end)' "$tableau" >"$tableau.new" && mv "$tableau.new" "$tableau"
done
jq --arg w "$WORKSPACE_ID" --arg e "$env" --arg l "$AZURE_LOCATION" \
  'walk(if type == "string" then gsub("\\$WORKSPACE_ID"; $w) | gsub("\\$ENV"; $e) | gsub("\\$LOCATION"; $l) else . end)' \
  "$tableau" >"$tableau.new" && mv "$tableau.new" "$tableau"
# create (PUT, relançable) ne lit que les propriétés ; import garderait le fichier entier mais perdrait les tags
jq '.properties' "$tableau" >"$tableau.new" && mv "$tableau.new" "$tableau"
az portal dashboard create -n "vigie-$env" -g "$RG" -l "$AZURE_LOCATION" --tags "hidden-title=vigie-$env" \
  --input-path "$tableau" -o none

echo "⑧ ✔ $appi branché sur les 5 apps et la Function ($env). Chaîne de connexion non affichée."
echo "   Les anciens composants acerolaz-calcul-$env sont conservés (à retirer à la main une fois la vigie validée)."
echo "   Le prochain déploiement exige le secret appinsights-connection sur chaque app."
