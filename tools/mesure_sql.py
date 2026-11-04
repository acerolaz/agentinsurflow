"""Mesures SQL du critère 2.3 : requête hybride réelle et vue minimisée, à plusieurs volumes.

Textes du corpus réel, vecteurs et dossiers SYNTHÉTIQUES : la latence se transpose en ordre de
grandeur, pas la pertinence. À lancer sur une base JETABLE, jamais sur une base utile :
le script vide `chunk`, `document` et les tables de dossiers qu'il remplit. Voir
`docs/donnees/requetes-sql.md` § 5.

    uv run python tools/mesure_sql.py <dsn vecteurs> <dsn dossiers>
"""

import asyncio
import glob
import json
import re
import statistics
import sys
from pathlib import Path

import asyncpg

from agentinsurflow_rag.infrastructure.postgres.corpus import SQL_HYBRIDE

VOLUMES_CHUNKS = (129, 5000, 20000)
VOLUMES_CONTRATS = (6, 1000, 10000)
NB_MESURES = 50
COLLECTIONS = ["textes_reglementaires", "notices_produits", "procedures_internes", "cgv_conditions"]
CANDIDATS, K = 20, 5
VECTEUR = (
    "(SELECT array_agg(x + (random()::real - 0.5) * 0.5)::vector "
    "FROM unnest((SELECT v FROM centre WHERE i = 1 + ({n}) % 50)) x)"
)


def vers_asyncpg(sql: str) -> str:
    """`:nom` de SQLAlchemy vers `$n` d'asyncpg, sans toucher aux `::type`."""
    noms = ["v", "collections", "candidats", "question", "k"]
    for rang, nom in enumerate(noms, 1):
        sql = re.sub(rf"(?<!:):{nom}\b", f"${rang}", sql)
    return sql.replace("CAST($1 AS vector)", "$1::vector").replace("ANY($2)", "ANY($2::text[])")


def resume(temps: list[float]) -> str:
    centiles = statistics.quantiles(temps, n=20)
    return f"médiane {statistics.median(temps):.2f} ms, p95 {centiles[18]:.2f} ms"


def noeuds(plan: dict) -> set[str]:
    ici = {f"{plan['Node Type']} ({plan['Index Name']})"} if "Index Name" in plan else set()
    for fils in plan.get("Plans", []):
        ici |= noeuds(fils)
    return ici


async def expliquer(
    con: asyncpg.Connection, sql: str, *args: object
) -> tuple[float, set[str], int]:
    lignes = await con.fetchval(f"EXPLAIN (ANALYZE, FORMAT JSON) {sql}", *args)
    racine = json.loads(lignes)[0]
    return racine["Execution Time"], noeuds(racine["Plan"]), racine["Plan"]["Actual Rows"]


async def remplir_chunks(con: asyncpg.Connection, textes: list[str], volume: int) -> float:
    await con.execute("TRUNCATE document CASCADE")
    await con.execute("DROP INDEX IF EXISTS chunk_embedding_hnsw")
    await con.executemany(
        "INSERT INTO document (doc_id, collection, version, etat, url_source, hash_contenu, "
        "extrait_le) VALUES ($1, $2, 'v1', 'VIGUEUR', 'https://exemple.invalid', "
        "repeat('0', 64), CURRENT_DATE)",
        [(f"d{n}", COLLECTIONS[n % 4]) for n in range(volume)],
    )
    await con.executemany(
        "INSERT INTO chunk (document_id, article, ordre, texte, embedding) "
        "SELECT id, 'A' || $1, 0, $2, "
        + VECTEUR.format(n="$1::int")
        + " FROM document WHERE doc_id = 'd' || $1",
        [(str(n), textes[n % len(textes)]) for n in range(volume)],
    )
    debut = asyncio.get_running_loop().time()
    await con.execute(
        "CREATE INDEX chunk_embedding_hnsw ON chunk USING hnsw (embedding vector_cosine_ops)"
    )
    duree = asyncio.get_running_loop().time() - debut
    await con.execute("ANALYZE document")
    await con.execute("ANALYZE chunk")
    return duree


async def mesurer_hybride(dsn: str, textes: list[str], questions: list[str]) -> None:
    con = await asyncpg.connect(dsn)
    await con.execute(
        "CREATE TEMP TABLE centre AS SELECT i, array(SELECT random()::real "
        "FROM generate_series(1, 1536 + (i - i))) AS v FROM generate_series(1, 50) i"
    )
    sql = vers_asyncpg(str(SQL_HYBRIDE))
    for volume in VOLUMES_CHUNKS:
        index_s = await remplir_chunks(con, textes, volume)
        for titre, reglage in (("avec index", "on"), ("témoin sans index", "off")):
            await con.execute(
                f"SET enable_indexscan = {reglage}; SET enable_bitmapscan = {reglage}"
            )
            temps, plans, rendus = [], set(), []
            for n in range(NB_MESURES):
                v = await con.fetchval(f"SELECT {VECTEUR.format(n=n)}::text")
                duree, plan, nb = await expliquer(
                    con, sql, v, COLLECTIONS, CANDIDATS, questions[n % len(questions)], K
                )
                temps.append(duree)
                plans |= plan
                rendus.append(nb)
            print(
                f"hybride|{volume}|{titre}|index {index_s:.1f} s|{resume(temps)}"
                f"|lignes min {min(rendus)}"
            )
            if reglage == "on":
                print("  plan : " + ", ".join(sorted(p for p in plans if "chunk" in p)))
    await con.execute("SET enable_indexscan = on; SET enable_bitmapscan = on")
    await con.close()


async def remplir_contrats(con: asyncpg.Connection, volume: int) -> None:
    await con.execute("TRUNCATE souscripteur, contrat, releve_information, sinistre CASCADE")
    await con.execute(
        """
        INSERT INTO souscripteur (id, nom, prenom, date_naissance, adresse, email, telephone,
                                  situation_familiale, permis_numero, permis_date_obtention,
                                  permis_pays, code_postal, civilite)
        SELECT md5('s' || n)::uuid, 'Nom' || n, 'Prenom' || n, DATE '1980-01-01' + n % 9000,
               'rue Fictive', 'x@exemple.invalid', '0600000000', 'celibataire', 'P' || n,
               DATE '2005-01-01' + n % 3000, 'FR',
               lpad((n % 95 + 1)::text, 2, '0') || '000', 'M.'
        FROM generate_series(1, $1) n
        """,
        volume,
    )
    await con.execute(
        """
        INSERT INTO contrat (id, numero_contrat, souscripteur_id, gestionnaire_id, date_effet,
                             statut, formule, mis_a_jour)
        SELECT md5('c' || n)::uuid, 'AIF-2026-' || lpad(n::text, 6, '0'), md5('s' || n)::uuid,
               'g' || (n % 20),
               DATE '2026-01-01', 'actif', 'tiers', now()
        FROM generate_series(1, $1) n
        """,
        volume,
    )
    await con.execute(
        """
        INSERT INTO releve_information (id, contrat_id, crm_bonus_malus, nb_suspensions_permis,
                                        nb_resiliations)
        SELECT md5('r' || n)::uuid, md5('c' || n)::uuid, 1, 0, 0 FROM generate_series(1, $1) n
        """,
        volume,
    )
    await con.execute(
        """
        INSERT INTO sinistre (id, releve_information_id, date_sinistre, nature, taux_responsabilite)
        SELECT md5('i' || n)::uuid, md5('r' || n)::uuid, DATE '2025-01-01', 'materiel', 1
        FROM generate_series(1, $1) n WHERE n % 3 = 0
        """,
        volume,
    )
    await con.execute(
        "ANALYZE souscripteur; ANALYZE contrat; ANALYZE releve_information; ANALYZE sinistre"
    )


async def mesurer_vue(dsn: str) -> None:
    con = await asyncpg.connect(dsn)
    un = "SELECT * FROM vue_contrat_minimisee WHERE gestionnaire_id = $1 AND numero_contrat = $2"
    page = (
        "SELECT * FROM vue_contrat_minimisee WHERE gestionnaire_id = $1 "
        "ORDER BY numero_contrat LIMIT 20"
    )
    for volume in VOLUMES_CONTRATS:
        await remplir_contrats(con, volume)
        for titre, sql, cle in (("un contrat", un, True), ("portefeuille, 20 lignes", page, False)):
            temps, plans, rendus = [], set(), []
            for n in range(NB_MESURES):
                numero = 1 + n * 7 % volume
                args = (
                    (f"g{numero % 20}", f"AIF-2026-{numero:06d}") if cle else (f"g{numero % 20}",)
                )
                duree, plan, nb = await expliquer(con, sql, *args)
                temps.append(duree)
                plans |= plan
                rendus.append(nb)
            print(f"vue|{volume}|{titre}|{resume(temps)}|lignes max {max(rendus)}")
            print("  plan : " + ", ".join(sorted(p for p in plans if "contrat" in p)))
    await con.close()


def charger_corpus() -> list[str]:
    fichier = sorted(glob.glob("data/aggregated/corpus-*.json"))[-1]
    entrees = json.loads(Path(fichier).read_text(encoding="utf-8"))["entrees"]
    return [re.sub(r"<[^>]+>", " ", e["texte_html"]) for e in entrees]


async def principal(dsn_vecteurs: str, dsn_dossiers: str) -> None:
    questions = [
        json.loads(ligne)["question"]
        for ligne in Path("eval/golden.jsonl").read_text(encoding="utf-8").splitlines()
        if ligne.strip()
    ]
    await mesurer_hybride(dsn_vecteurs, charger_corpus(), questions)
    await mesurer_vue(dsn_dossiers)


if __name__ == "__main__":
    asyncio.run(principal(sys.argv[1], sys.argv[2]))
