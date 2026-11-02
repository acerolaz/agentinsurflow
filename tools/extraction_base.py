"""Extraction depuis la base de données ``dossiers`` (``make extraire-base``).

Se connecte à PostgreSQL avec le compte ``dossiers`` (droits limités), lit la vue minimisée et écrit
``dossiers-agregats-<date>.json`` au format des autres collectes : manifeste + lignes. Seuls des
agrégats sortent : ni numéro de contrat, ni gestionnaire, ni département, ni observations.

Les six parties du traitement sont visibles : point de lancement (``main``), initialisation
(``_options_connexion``, connexion), règles de traitement (``REQUETE``, ``extraire``), gestion des
erreurs (``ErreurBase`` et ``main``), fin de traitement (connexion fermée dans ``finally``, résumé
affiché), sauvegarde (``sauvegarder_instantane``, écriture atomique).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Awaitable, Callable, Sequence
from datetime import date as Date
from pathlib import Path
from typing import Any

import asyncpg

from agentinsurflow_rag.cli.ingest import sauvegarder_instantane

REQUETE = """
SELECT formule, tranche_age,
       count(*)::int AS nb_dossiers,
       round(avg(crm_bonus_malus)::numeric, 2)::float8 AS crm_moyen,
       round(avg(nb_sinistres)::numeric, 2)::float8 AS sinistres_moyens,
       count(*) FILTER (WHERE releve_present)::int AS avec_releve
FROM vue_contrat_minimisee
GROUP BY formule, tranche_age
ORDER BY formule, tranche_age
"""
Connecteur = Callable[..., Awaitable[Any]]


class ErreurBase(Exception):
    """Extraction impossible : aucun instantané n'est écrit."""


def _options_connexion() -> dict[str, Any]:
    mot_de_passe = os.environ.get("PG_DOSSIERS_PASSWORD")
    if not mot_de_passe:
        raise ErreurBase("PG_DOSSIERS_PASSWORD absent (.env)")
    return {
        "host": os.environ.get("PG_HOST", "localhost"),
        "port": int(os.environ.get("PG_PORT", "5432")),
        "database": "dossiers",
        "user": "dossiers",
        "password": mot_de_passe,
        "timeout": 10,
    }


async def extraire(connecter: Connecteur) -> list[dict[str, Any]]:
    connexion = await connecter(**_options_connexion())
    try:
        lignes = [dict(ligne) for ligne in await connexion.fetch(REQUETE)]
    finally:
        await connexion.close()
    if not lignes:
        raise ErreurBase("aucun dossier dans la base : lancer les migrations avec les SEED_*")
    return lignes


def main(argv: Sequence[str] | None = None, connecter: Connecteur = asyncpg.connect) -> int:
    parseur = argparse.ArgumentParser(description=__doc__)
    parseur.add_argument("--sortie", type=Path, default=Path("data/raw"))
    parseur.add_argument("--date", default=Date.today().isoformat())
    parseur.add_argument("--environnement", default=os.environ.get("APP_ENV", "local"))
    args = parseur.parse_args(argv)
    try:
        lignes = asyncio.run(extraire(connecter))
    except (ErreurBase, OSError, ValueError, asyncpg.PostgresError) as erreur:
        print(f"✘ extraction interrompue : {erreur}", file=sys.stderr)
        return 1
    chemin = sauvegarder_instantane(
        lignes,
        args.sortie,
        args.environnement,
        args.date,
        prefixe="dossiers-agregats",
        perimetre="vue_contrat_minimisee",
    )
    print(f"✔ instantané {chemin} ({len(lignes)} lignes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
