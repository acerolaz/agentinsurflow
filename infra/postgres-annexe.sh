#!/usr/bin/env bash
# Base PostgreSQL annexe des Container Apps (G5, avancée depuis U5 ; S3-5, S3-12, S3-19).
# `make annexe` (lit le .env via le Makefile). Idempotent. Lancé par Acerola AVANT le merge de G5 :
# infra/containerapp-postgres.yaml référence l'image et les secrets posés ici.
# Base éphémère (S3-5) : chaque révision repart vide ; le corpus revient par l'ingestion.
set -euo pipefail

for v in AZURE_RESOURCE_GROUP ACR_NAME UW_APP_STAGING UW_APP_PRODUCTION RAG_APP_STAGING RAG_APP_PRODUCTION PG_APP_STAGING PG_APP_PRODUCTION PG_POSTGRES_PASSWORD \
  PG_MIGRATEUR_PASSWORD PG_WRITER_PASSWORD PG_READER_PASSWORD PG_DOSSIERS_PASSWORD \
  PG_TRACES_WRITER_PASSWORD PG_TRACES_READER_PASSWORD; do
  [ -n "${!v:-}" ] || { echo "✘ $v manquant dans .env"; exit 1; }
done
# ponytail: tag fixe, à incrémenter ici et dans deploy.yml quand infra/postgres/ change
image="$ACR_NAME.azurecr.io/agentinsurflow-postgres:1"

echo "① Image annexe (pgvector, bases et comptes créés au premier démarrage)"
az acr login -n "$ACR_NAME"
docker build --platform linux/amd64 -t "$image" infra/postgres
docker push "$image"

echo "② Secrets PostgreSQL : chaque app n'a que ceux dont elle se sert (postgres : les sept, underwriting-admin : quatre, rag : trois)"
for app in "$PG_APP_STAGING" "$PG_APP_PRODUCTION"; do
  az containerapp secret set -n "$app" -g "$AZURE_RESOURCE_GROUP" -o none --secrets \
    "pg-postgres-password=$PG_POSTGRES_PASSWORD" \
    "pg-migrateur-password=$PG_MIGRATEUR_PASSWORD" \
    "pg-writer-password=$PG_WRITER_PASSWORD" \
    "pg-reader-password=$PG_READER_PASSWORD" \
    "pg-dossiers-password=$PG_DOSSIERS_PASSWORD" \
    "pg-traces-writer-password=$PG_TRACES_WRITER_PASSWORD" \
    "pg-traces-reader-password=$PG_TRACES_READER_PASSWORD"
done
# underwriting-admin (#70) a sa propre Container App : dossiers et traces ; la principale (gateway) n'en a plus l'usage
for app in "$UW_APP_STAGING" "$UW_APP_PRODUCTION"; do
  az containerapp secret set -n "$app" -g "$AZURE_RESOURCE_GROUP" -o none --secrets \
    "pg-migrateur-password=$PG_MIGRATEUR_PASSWORD" \
    "pg-dossiers-password=$PG_DOSSIERS_PASSWORD" \
    "pg-traces-writer-password=$PG_TRACES_WRITER_PASSWORD" \
    "pg-traces-reader-password=$PG_TRACES_READER_PASSWORD"
done
# rag (#70) a sa propre Container App : ses trois comptes seulement (migrateur au démarrage, writer, reader)
for app in "$RAG_APP_STAGING" "$RAG_APP_PRODUCTION"; do
  az containerapp secret set -n "$app" -g "$AZURE_RESOURCE_GROUP" -o none --secrets \
    "pg-migrateur-password=$PG_MIGRATEUR_PASSWORD" \
    "pg-writer-password=$PG_WRITER_PASSWORD" \
    "pg-reader-password=$PG_READER_PASSWORD"
done
echo "✔ Annexe prête : le prochain déploiement pose la Container App postgres"
