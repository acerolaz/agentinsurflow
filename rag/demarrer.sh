#!/bin/sh
# Démarrage de rag (spec §1, §2.3) : la base annexe est éphémère, chaque révision repart vide.
# 1. migrations de « vecteurs » avec le compte migrateur, en attendant PostgreSQL (60 s au plus) ;
# 2. le mot de passe de migrateur est retiré de l'environnement : les routes n'utilisent que
#    writer et reader (séparation par processus) ;
# 3. uvicorn remplace le shell (signaux reçus directement).
set -eu

if [ -n "${PG_MIGRATEUR_PASSWORD:-}" ]; then
  attente=0
  until alembic -n vecteurs upgrade head; do
    attente=$((attente + 2))
    [ "$attente" -lt 60 ] || { echo "migrations impossibles après 60 s" >&2; exit 1; }
    sleep 2
  done
fi
unset PG_MIGRATEUR_PASSWORD

# pas de journal d'accès : il écrirait la query string (/api/extraits?question=…, RGPD)
exec uvicorn agentinsurflow_rag.api:app --host 0.0.0.0 --port 8001 --no-access-log
