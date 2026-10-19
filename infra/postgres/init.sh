#!/bin/bash
# Bases et comptes de la solution (exécuté une fois, base vide, par docker-entrypoint-initdb.d).
#   vecteurs  (rag)                : migrateur (propriétaire), writer, reader ; extension vector
#   dossiers  (underwriting-admin) : migrateur (propriétaire), dossiers
#   traces    (underwriting-admin) : migrateur (propriétaire), traces_writer, traces_reader
# Les droits sur les tables sont posés par les migrations (Alembic, EF Core), pas ici.
# PG_BASES_TEST=1 crée aussi vecteurs_test, dossiers_test et traces_test.
set -euo pipefail

for variable in PG_MIGRATEUR_PASSWORD PG_WRITER_PASSWORD PG_READER_PASSWORD PG_DOSSIERS_PASSWORD \
  PG_TRACES_WRITER_PASSWORD PG_TRACES_READER_PASSWORD; do
  : "${!variable:?$variable manquant}"
done

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v migrateur="$PG_MIGRATEUR_PASSWORD" -v writer="$PG_WRITER_PASSWORD" \
  -v reader="$PG_READER_PASSWORD" -v dossiers="$PG_DOSSIERS_PASSWORD" \
  -v traces_writer="$PG_TRACES_WRITER_PASSWORD" -v traces_reader="$PG_TRACES_READER_PASSWORD" <<'SQL'
CREATE ROLE migrateur LOGIN PASSWORD :'migrateur';
CREATE ROLE writer LOGIN PASSWORD :'writer';
CREATE ROLE reader LOGIN PASSWORD :'reader';
CREATE ROLE dossiers LOGIN PASSWORD :'dossiers';
CREATE ROLE traces_writer LOGIN PASSWORD :'traces_writer';
CREATE ROLE traces_reader LOGIN PASSWORD :'traces_reader';
SQL

bases="vecteurs dossiers traces"
if [ "${PG_BASES_TEST:-0}" = 1 ]; then
  bases="$bases vecteurs_test dossiers_test traces_test"
fi

for base in $bases; do
  case "$base" in
    vecteurs*) comptes="writer, reader" ;;
    dossiers*) comptes="dossiers" ;;
    traces*) comptes="traces_writer, traces_reader" ;;
  esac
  # personne d'autre que les comptes prévus ne s'y connecte
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
    -c "CREATE DATABASE $base OWNER migrateur" \
    -c "REVOKE ALL ON DATABASE $base FROM PUBLIC" \
    -c "GRANT CONNECT ON DATABASE $base TO $comptes"
  if [[ "$base" == vecteurs* ]]; then
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$base" \
      -c "CREATE EXTENSION IF NOT EXISTS vector"
  fi
done
