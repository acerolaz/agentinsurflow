"""Extraction big data freMTPL2 en PySpark et Spark SQL (``make bigdata``).

Lit les ARFF freMTPL2freq et freMTPL2sev (téléchargés dans le cache, SHA-256 vérifié), les
convertit en Parquet, exécute deux requêtes Spark SQL (fréquence par région ; coût moyen par
tranche de bonus-malus, avec une jointure ``BROADCAST``) et écrit un instantané
``fremtpl2-agregats-<date>.json`` au format des autres collectes (manifeste + lignes).

Les six parties du traitement sont visibles : point de lancement (``main``), initialisation
(``session_spark``, ``telecharger``), règles de traitement (``vers_parquet``, ``REQUETES``,
``executer``), gestion des erreurs (``ErreurBigData`` et ``main``), fin de traitement (session
arrêtée dans ``finally``, résumé affiché), sauvegarde (``sauvegarder_instantane``).
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from datetime import date as Date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from entrainement.donnees import (
    BONUS_MALUS_MAX,
    BONUS_MALUS_MIN,
    EXPOSURE_MAX,
    SOURCE_SEV,
    attributs,
    telecharger,
)

from agentinsurflow_rag.cli.ingest import sauvegarder_instantane

if TYPE_CHECKING:
    from pyspark.sql import SparkSession

MSG_JAVA = "Java 17 requis : brew install openjdk@17"
PERIMETRE = "freMTPL2freq×freMTPL2sev (OpenML 41214, 41215)"

# Bornes de préparation partagées avec le GLM (entrainement.donnees) ; hors bornes = exclu.
_FILTRE = (
    f"freq.Exposure > 0 AND freq.Exposure <= {EXPOSURE_MAX:g} "
    f"AND freq.BonusMalus BETWEEN {BONUS_MALUS_MIN} AND {BONUS_MALUS_MAX}"
)

REQUETES: dict[str, str] = {
    "frequence_par_region": f"""
        SELECT Region,
               COUNT(*) AS contrats,
               SUM(Exposure) AS exposition,
               SUM(ClaimNb) AS sinistres,
               SUM(ClaimNb) / SUM(Exposure) AS frequence
        FROM freq
        WHERE {_FILTRE}
        GROUP BY Region
        ORDER BY Region
    """,
    "cout_moyen_par_bonus_malus": f"""
        WITH couts AS (
            SELECT IDpol, SUM(ClaimAmount) AS montant, COUNT(*) AS nb
            FROM sev
            GROUP BY IDpol
        )
        SELECT /*+ BROADCAST(couts) */
               CASE WHEN freq.BonusMalus < 100 THEN '50-99'
                    WHEN freq.BonusMalus < 150 THEN '100-149'
                    ELSE '150-230' END AS tranche_bm,
               COUNT(DISTINCT freq.IDpol) AS contrats_sinistres,
               SUM(couts.montant) / SUM(couts.nb) AS cout_moyen
        FROM freq
        JOIN couts ON freq.IDpol = couts.IDpol
        WHERE {_FILTRE}
        GROUP BY tranche_bm
        ORDER BY MIN(freq.BonusMalus)
    """,
}


class ErreurBigData(Exception):
    """Environnement Spark inutilisable : aucun instantané n'est écrit."""


def session_spark() -> SparkSession:
    """Session Spark locale ; ``ErreurBigData`` claire si Java est introuvable."""
    from py4j.protocol import Py4JError
    from pyspark.errors import PySparkRuntimeError
    from pyspark.sql import SparkSession

    try:  # couvre Java absent, stub /usr/bin/java ou JAVA_HOME inexistant
        return (
            SparkSession.builder.master("local[*]").appName("agentinsurflow-bigdata").getOrCreate()
        )
    except (PySparkRuntimeError, Py4JError) as erreur:
        raise ErreurBigData(MSG_JAVA) from erreur


def vers_parquet(spark: SparkSession, arff: Path, parquet: Path) -> None:
    """ARFF -> Parquet : lignes ``@`` ignorées (commentaires), noms issus de ``attributs``."""
    df = spark.read.csv(str(arff), comment="@", quote="'", inferSchema=True)
    df.toDF(*attributs(arff)).write.mode("overwrite").parquet(str(parquet))


def executer(spark: SparkSession, parquet_freq: Path, parquet_sev: Path) -> list[dict[str, Any]]:
    """Enregistre les vues ``freq`` et ``sev``, exécute ``REQUETES`` : une ligne par résultat."""
    spark.read.parquet(str(parquet_freq)).createOrReplaceTempView("freq")
    spark.read.parquet(str(parquet_sev)).createOrReplaceTempView("sev")
    return [
        {"requete": nom, **ligne.asDict()}
        for nom, sql in REQUETES.items()
        for ligne in spark.sql(sql).collect()
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parseur = argparse.ArgumentParser(description=__doc__)
    parseur.add_argument(
        "--cache",
        type=Path,
        default=Path(os.environ.get("FREMTPL2_CACHE", "/tmp/fremtpl2-cache")),
    )
    parseur.add_argument("--sortie", type=Path, default=Path("data/raw"))
    parseur.add_argument("--date", default=Date.today().isoformat())
    parseur.add_argument(
        "--expliquer", action="store_true", help="affiche le plan de chaque requête"
    )
    args = parseur.parse_args(argv)
    from py4j.protocol import Py4JError
    from pyspark.errors import PySparkException

    spark = None
    try:
        spark = session_spark()  # Java vérifié avant tout téléchargement
        args.cache.mkdir(parents=True, exist_ok=True)
        arff_freq, arff_sev = telecharger(args.cache), telecharger(args.cache, SOURCE_SEV)
        parquet_freq, parquet_sev = args.cache / "freq.parquet", args.cache / "sev.parquet"
        vers_parquet(spark, arff_freq, parquet_freq)
        vers_parquet(spark, arff_sev, parquet_sev)
        lignes = executer(spark, parquet_freq, parquet_sev)
        if args.expliquer:
            for sql in REQUETES.values():
                spark.sql(sql).explain("formatted")
        chemin = sauvegarder_instantane(
            lignes,
            args.sortie,
            "local",
            args.date,
            prefixe="fremtpl2-agregats",
            perimetre=PERIMETRE,
        )
    except (ErreurBigData, ValueError, OSError, PySparkException, Py4JError) as erreur:
        print(f"✘ extraction interrompue : {erreur}", file=sys.stderr)
        return 1
    finally:
        if spark is not None:
            spark.stop()
    print(f"✔ instantané {chemin} ({len(lignes)} lignes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
