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
    --input-path)
      # portal 1.0.0b2 : create lit les seules propriétés (lenses et metadata à la racine)
      [[ "$args" != *"portal dashboard create"* ]] || jq -e 'has("lenses") and has("metadata")' "$a" >/dev/null ||
        { echo "faux az : Failed to parse 'lenses' from property." >&2; exit 2; }
      cp "$a" "$FAUX_AZ_JOURNAL.input" # vigie.sh supprime son fichier temporaire en sortant
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
