#!/usr/bin/env bash
# Faux `az` des tests de vigie.sh : journalise un appel par ligne, répond des valeurs factices.
# Jamais d'accès à Azure.
args="$*"
printf '%s\n' "${args//$'\n'/ }" >>"${FAUX_AZ_JOURNAL:?}"
case "$args" in
  *"--query connectionString"*) echo "chaine-factice" ;;
  *"--query properties.configuration.ingress.fqdn"*) echo "gw.exemple" ;;
  *"--query id"*) echo "/subscriptions/x/resourceGroups/rg/providers/fictif/ressource" ;;
esac
exit 0
