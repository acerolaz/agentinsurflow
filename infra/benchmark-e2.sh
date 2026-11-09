#!/usr/bin/env bash
# Benchmark C7 : secret temporaire de agentinsurflow-rag pour le rag local, le temps de la campagne.
# Lancé À LA MAIN par Acerola, jamais par un agent ni par la CI, depuis la racine du worktree.
#   infra/benchmark-e2.sh creer    : ajoute au .env local LLM_AUDIENCE, RAG_SEUIL, RAG_CLIENT_SECRET
#   infra/benchmark-e2.sh retirer  : supprime ce secret dans Entra et la ligne RAG_CLIENT_SECRET du .env
# Portée : agentinsurflow-rag (RAG_API_CLIENT_ID) est la MÊME inscription en staging et en production (variable
# du dépôt) et porte le rôle LLM : tant qu'il vit, ce secret ouvre le LLM de production. Le retirer dès la fin.
# Le secret expire seul 24 h après sa création (heure UTC comprise). Il n'est jamais affiché ; .env reste ignoré
# par Git. macOS seulement (date -v).
set -euo pipefail

NOM=benchmark-e2
[ -f .env ] || { echo "✘ .env absent : lancer depuis la racine du worktree" >&2; exit 1; }
APP=$(grep -E '^RAG_API_CLIENT_ID=' .env | cut -d= -f2)
[ -n "$APP" ] || { echo "✘ RAG_API_CLIENT_ID absent du .env" >&2; exit 1; }

case "${1:-}" in
creer)
  git check-ignore -q .env
  if grep -q '^RAG_CLIENT_SECRET=' .env; then
    echo "✘ RAG_CLIENT_SECRET déjà dans .env : rien créé" >&2
    exit 1
  fi
  # Affectations à part : dans un echo, set -e ne verrait pas l'échec de gh ou de az.
  audience=$(gh variable get LLM_AUDIENCE)
  seuil=$(gh variable get RAG_SEUIL)
  secret=$(az ad app credential reset --id "$APP" --append \
    --display-name "$NOM" --end-date "$(date -u -v+1d +%Y-%m-%dT%H:%M:%SZ)" --query password -o tsv)
  [ -n "$secret" ] || { echo "✘ az n'a rendu aucun secret" >&2; exit 1; }
  [ -z "$(tail -c1 .env)" ] || echo >>.env # dernière ligne sans saut : ne pas la prolonger
  printf 'LLM_AUDIENCE=%s\nRAG_SEUIL=%s\nRAG_CLIENT_SECRET=%s\n' "$audience" "$seuil" "$secret" >>.env
  echo "✔ .env complété ; retirer le secret après la campagne : infra/benchmark-e2.sh retirer"
  ;;
retirer)
  CLE=$(az ad app credential list --id "$APP" --query "[?displayName=='$NOM'].keyId" -o tsv)
  for id in $CLE; do az ad app credential delete --id "$APP" --key-id "$id"; done
  sed -i '' '/^RAG_CLIENT_SECRET=/d' .env # LLM_AUDIENCE et RAG_SEUIL ne sont pas secrets : laissés
  echo "✔ secret $NOM retiré (Entra et .env)"
  ;;
*)
  echo "usage : $0 creer|retirer" >&2
  exit 2
  ;;
esac
