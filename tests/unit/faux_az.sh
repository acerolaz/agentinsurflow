#!/usr/bin/env bash
# Faux `az` des tests de vigie.sh : journalise un appel par ligne, répond des valeurs factices.
# Jamais d'accès à Azure. Refuse (exit 2) les formes que le vrai az rejetterait.
args="$*"
printf '%s\n' "${args//$'\n'/ }" >>"${FAUX_AZ_JOURNAL:?}"
precedent=""
for a in "$@"; do
  case "$precedent" in
    --window-size | --evaluation-frequency)
      [[ "$a" =~ ^([0-9]+h)?([0-9]+m)?([0-9]+s)?$ ]] || { echo "faux az : durée invalide « $a » (##h##m##s)" >&2; exit 2; }
      ;;
    --kind)
      [ "$a" != standard ] || { echo "faux az : --kind standard invalide (--web-test-kind)" >&2; exit 2; }
      ;;
  esac
  precedent=$a
done
case "$args" in
  *"--query connectionString"*) echo "chaine-factice" ;;
  *"--query properties.configuration.ingress.fqdn"*) echo "gw.exemple" ;;
  *"--query id"*) echo "/subscriptions/x/resourceGroups/rg/providers/fictif/ressource" ;;
esac
exit 0
