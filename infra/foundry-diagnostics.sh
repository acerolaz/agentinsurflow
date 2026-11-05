#!/usr/bin/env bash
# Monitorage de la ressource Foundry (C8) : `make foundry-diag` (lit le .env). Idempotent.
# Lancé À LA MAIN par Acerola, jamais par un agent ni par la CI. Prérequis : az login, droit d'écrire les
# paramètres de diagnostic sur la ressource Foundry.
# Envoie AllMetrics (requêtes, tokens, latence, erreurs) et Audit vers l'espace Log Analytics du projet.
# RequestResponse n'est PAS activé : la documentation relevée ne garantit pas son contenu, et le texte d'une
# question n'est jamais tracé (rag/CLAUDE.md). À n'ajouter qu'après avoir vérifié ce que cette catégorie enregistre.
set -euo pipefail

for v in AZURE_RESOURCE_GROUP FOUNDRY_NAME FOUNDRY_RESOURCE_GROUP LOG_ANALYTICS_WORKSPACE; do
  [ -n "${!v:-}" ] || { echo "✘ $v manquant dans .env" >&2; exit 1; }
done
foundry=$(az cognitiveservices account show -n "$FOUNDRY_NAME" -g "$FOUNDRY_RESOURCE_GROUP" --query id -o tsv)
espace=$(az monitor log-analytics workspace show -n "$LOG_ANALYTICS_WORKSPACE" -g "$AZURE_RESOURCE_GROUP" --query id -o tsv)
az monitor diagnostic-settings create -n foundry-vers-log-analytics --resource "$foundry" --workspace "$espace" \
  --logs '[{"category":"Audit","enabled":true}]' \
  --metrics '[{"category":"AllMetrics","enabled":true}]' -o none
echo "✔ diagnostics de $FOUNDRY_NAME envoyés vers $LOG_ANALYTICS_WORKSPACE (données visibles sous deux heures au plus)"
