#!/usr/bin/env bash
# Lie un domaine personnalisé à la Container App de production, avec certificat managé (G4, S3-28, #12).
# `make domaine DOMAINE=api.exemple.fr` (lit le .env via le Makefile). Idempotent. Lancé par Acerola.
# Prérequis : az login (Contributor sur le groupe de ressources), dig, et l'accès à la zone DNS du domaine.
set -euo pipefail

domaine=${1:?usage : infra/domaine.sh <domaine>}
for v in AZURE_RESOURCE_GROUP CONTAINERAPPS_ENV APP_PRODUCTION; do
  [ -n "${!v:-}" ] || { echo "✘ $v manquant dans .env"; exit 1; }
done
RG=$AZURE_RESOURCE_GROUP
app=$APP_PRODUCTION

lie=$(az containerapp hostname list -n "$app" -g "$RG" --query "[?name=='$domaine'].bindingType" -o tsv)
if [ "$lie" = "SniEnabled" ]; then
  echo "✔ $domaine est déjà lié à $app avec un certificat"
  exit 0
fi

id=$(az containerapp show -n "$app" -g "$RG" --query properties.customDomainVerificationId -o tsv)
# ponytail: un seul point = apex ; faux pour un suffixe à deux niveaux (exemple.co.uk)
if [ "${domaine//[^.]/}" = "." ]; then
  type=A
  cible=$(az containerapp env show -n "$CONTAINERAPPS_ENV" -g "$RG" --query properties.staticIp -o tsv)
  methode=HTTP # 🔴 à vérifier : validation d'un apex pour le certificat managé
else
  type=CNAME
  cible=$(az containerapp show -n "$app" -g "$RG" --query properties.configuration.ingress.fqdn -o tsv)
  methode=CNAME
fi

echo "① Enregistrements DNS à créer dans la zone de $domaine :"
printf '   %-5s %-40s %s\n' "$type" "$domaine" "$cible" TXT "asuid.$domaine" "$id"

echo "② Attente de la résolution DNS (10 min au plus)"
# Serveur de noms qui fait autorité : un résolveur local garde l'ancienne valeur jusqu'à la fin du TTL
zone=$domaine
[ "$type" = A ] || zone=${domaine#*.}
ns=$(dig +short "$zone" NS | head -1)
resout() { dig +short @"$ns" "$2" "$1" | tr -d '"' | sed 's/\.$//' | grep -qxF -- "$3"; }
for i in $(seq 60); do
  resout "$type" "$domaine" "$cible" && resout TXT "asuid.$domaine" "$id" && break
  [ "$i" -lt 60 ] || { echo "✘ DNS pas encore propagé : relancer le script plus tard"; exit 1; }
  sleep 10
done

echo "③ Liaison et certificat managé"
[ -n "$lie" ] || az containerapp hostname add --hostname "$domaine" -n "$app" -g "$RG" -o none
az containerapp hostname bind --hostname "$domaine" -n "$app" -g "$RG" \
  --environment "$CONTAINERAPPS_ENV" --validation-method "$methode" -o none
echo "✔ https://$domaine sert $app. Ensuite : variable GitHub PROD_URL=https://$domaine"
echo "  et, en G5, l'URI de redirection Swagger dans infra/entra.sh."
