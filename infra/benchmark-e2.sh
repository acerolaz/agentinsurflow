#!/usr/bin/env bash
# Benchmark C7 : secret temporaire de agentinsurflow-rag pour le rag local, le temps de la campagne.
# Lancé À LA MAIN par Acerola, jamais par un agent ni par la CI, depuis la racine du worktree.
#   infra/benchmark-e2.sh creer    : ajoute au .env local LLM_AUDIENCE, RAG_SEUIL, RAG_CLIENT_SECRET
#   infra/benchmark-e2.sh retirer  : supprime ce secret dans Entra
# Le secret expire seul le lendemain. Il n'est jamais affiché ; .env reste ignoré par Git.
set -euo pipefail

NOM=benchmark-e2
APP=$(grep -E '^RAG_API_CLIENT_ID=' .env | cut -d= -f2)

case "${1:-}" in
creer)
  git check-ignore -q .env
  {
    echo "LLM_AUDIENCE=$(gh variable get LLM_AUDIENCE)"
    echo "RAG_SEUIL=$(gh variable get RAG_SEUIL)"
    echo "RAG_CLIENT_SECRET=$(az ad app credential reset --id "$APP" --append \
      --display-name "$NOM" --end-date "$(date -v+1d +%Y-%m-%d)" --query password -o tsv)"
  } >>.env
  echo "✔ .env complété ; retirer le secret après la campagne : infra/benchmark-e2.sh retirer"
  ;;
retirer)
  CLE=$(az ad app credential list --id "$APP" --query "[?displayName=='$NOM'].keyId" -o tsv)
  for id in $CLE; do az ad app credential delete --id "$APP" --key-id "$id"; done
  echo "✔ secret $NOM retiré"
  ;;
*)
  echo "usage : $0 creer|retirer" >&2
  exit 2
  ;;
esac
