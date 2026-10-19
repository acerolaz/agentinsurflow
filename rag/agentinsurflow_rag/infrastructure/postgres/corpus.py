"""Adaptateur PostgreSQL du port ``DepotCorpus`` (base ``vecteurs``, SQL paramétré, Core async).

Une instance enveloppe la connexion de la requête : sa transaction est celle de la route.
"""

from __future__ import annotations

import json
from dataclasses import fields
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

from ...domain.models import (
    ArticlePropre,
    ChunkDocument,
    CitationRag,
    DocumentTrace,
    EtatCorpus,
    Extrait,
    IngestionJournalisee,
    VersionDocument,
)

RRF_K = 60

# Deux classements (cosinus HNSW, plein texte GIN), fusionnés par RRF : Σ 1 / (60 + rang).
# ts_rank_cd n'est pas BM25 (pas d'IDF) : écart assumé (S3-11).
SQL_HYBRIDE = text(
    f"""
    WITH vect AS (
        SELECT c.id, row_number() OVER (ORDER BY c.embedding <=> CAST(:v AS vector)) AS rang
        FROM chunk c JOIN document d ON d.id = c.document_id
        WHERE NOT d.obsolete AND d.collection = ANY(:collections)
        ORDER BY c.embedding <=> CAST(:v AS vector)
        LIMIT :candidats
    ), plein_texte AS (
        SELECT c.id, row_number() OVER (ORDER BY ts_rank_cd(c.tsv, q) DESC) AS rang
        FROM chunk c JOIN document d ON d.id = c.document_id,
             websearch_to_tsquery('french', :question) q
        WHERE NOT d.obsolete AND d.collection = ANY(:collections) AND c.tsv @@ q
        ORDER BY ts_rank_cd(c.tsv, q) DESC
        LIMIT :candidats
    ), fusion AS (
        SELECT id, sum(1.0 / ({RRF_K} + rang)) AS score
        FROM (SELECT id, rang FROM vect UNION ALL SELECT id, rang FROM plein_texte) classements
        GROUP BY id
    )
    SELECT c.id AS chunk_id, c.article, c.texte, d.doc_id, d.version, d.collection,
           d.date_debut, d.url_source, f.score AS score_rrf,
           1 - (c.embedding <=> CAST(:v AS vector)) AS cosinus
    FROM fusion f JOIN chunk c ON c.id = f.id JOIN document d ON d.id = c.document_id
    ORDER BY f.score DESC, c.id
    LIMIT :k
    """
)

SQL_PAR_ARTICLES = text(
    """
    SELECT c.id AS chunk_id, c.article, c.texte, d.doc_id, d.version, d.collection,
           d.date_debut, d.url_source, 0.0 AS score_rrf, NULL AS cosinus
    FROM chunk c JOIN document d ON d.id = c.document_id
    WHERE NOT d.obsolete AND d.collection = ANY(:collections) AND c.article = ANY(:articles)
    ORDER BY array_position(CAST(:articles AS text[]), c.article), c.ordre
    """
)


def vecteur_sql(vecteur: list[float]) -> str:
    """Littéral pgvector, ex. ``[0.1,0.2]`` (le pilote le transmet en texte)."""
    return "[" + ",".join(f"{x:.8g}" for x in vecteur) + "]"


def _extrait(ligne: RowMapping) -> Extrait:
    citation = CitationRag(**{f.name: ligne[f.name] for f in fields(CitationRag)})
    cosinus = ligne["cosinus"]
    return Extrait(
        citation,
        ligne["texte"],
        None if cosinus is None else float(cosinus),
        float(ligne["score_rrf"]),
    )


def _ingestion(ligne: RowMapping) -> IngestionJournalisee:
    rapport = ligne["rapport"]
    return IngestionJournalisee(
        id=ligne["id"],
        instantane_sha256=ligne["instantane_sha256"],
        recu_le=ligne["recu_le"],
        rapport=rapport if isinstance(rapport, dict) else json.loads(rapport),
    )


class PgDepotCorpus:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def version_courante(self, doc_id: str) -> tuple[int, str, str] | None:
        ligne = (
            await self._conn.execute(
                text(
                    "SELECT id, version, hash_contenu FROM document "
                    "WHERE doc_id = :doc_id AND NOT obsolete"
                ),
                {"doc_id": doc_id},
            )
        ).first()
        return None if ligne is None else (ligne.id, ligne.version, ligne.hash_contenu)

    async def inserer(
        self,
        article: ArticlePropre,
        collection: str,
        chunks: list[str],
        vecteurs: list[list[float]],
    ) -> None:
        document_id = (
            await self._conn.execute(
                text(
                    "INSERT INTO document (doc_id, collection, version, date_debut, etat, "
                    "url_source, hash_contenu) VALUES (:doc_id, :collection, :version, "
                    ":date_debut, :etat, :url_source, :hash) RETURNING id"
                ),
                {
                    "doc_id": article.doc_id,
                    "collection": collection,
                    "version": article.version,
                    "date_debut": article.date_debut,
                    "etat": article.etat,
                    "url_source": article.url_source,
                    "hash": article.hash_contenu,
                },
            )
        ).scalar_one()
        await self._conn.execute(
            text(
                "INSERT INTO chunk (document_id, article, ordre, texte, embedding) "
                "VALUES (:document_id, :article, :ordre, :texte, CAST(:embedding AS vector))"
            ),
            [
                {
                    "document_id": document_id,
                    "article": article.article,
                    "ordre": ordre,
                    "texte": chunk,
                    "embedding": vecteur_sql(vecteur),
                }
                for ordre, (chunk, vecteur) in enumerate(zip(chunks, vecteurs, strict=True))
            ],
        )

    async def marquer_obsolete(self, document_id: int) -> None:
        await self._conn.execute(
            text("UPDATE document SET obsolete = true WHERE id = :id"), {"id": document_id}
        )

    async def voisins(
        self, vecteur: list[float], doc_id: str, seuil: float
    ) -> list[tuple[str, float]]:
        lignes = await self._conn.execute(
            text(
                "SELECT d.doc_id, max(1 - (c.embedding <=> CAST(:v AS vector))) AS score "
                "FROM chunk c JOIN document d ON d.id = c.document_id "
                "WHERE NOT d.obsolete AND d.doc_id <> :doc_id "
                "AND 1 - (c.embedding <=> CAST(:v AS vector)) > :seuil "
                "GROUP BY d.doc_id ORDER BY score DESC LIMIT 5"
            ),
            {"v": vecteur_sql(vecteur), "doc_id": doc_id, "seuil": seuil},
        )
        return [(ligne.doc_id, float(ligne.score)) for ligne in lignes]

    async def journaliser(self, instantane_sha256: str, rapport: dict[str, Any]) -> int:
        resultat = await self._conn.execute(
            text(
                "INSERT INTO ingestion (instantane_sha256, rapport) "
                "VALUES (:sha, CAST(:rapport AS jsonb)) RETURNING id"
            ),
            {"sha": instantane_sha256, "rapport": json.dumps(rapport, ensure_ascii=False)},
        )
        return int(resultat.scalar_one())

    async def rechercher_hybride(
        self,
        question: str,
        vecteur: list[float],
        collections: list[str],
        candidats: int,
        k: int,
    ) -> list[Extrait]:
        lignes = await self._conn.execute(
            SQL_HYBRIDE,
            {
                "v": vecteur_sql(vecteur),
                "question": question,
                "collections": collections,
                "candidats": candidats,
                "k": k,
            },
        )
        return [_extrait(ligne) for ligne in lignes.mappings()]

    async def par_articles(self, articles: list[str], collections: list[str]) -> list[Extrait]:
        lignes = await self._conn.execute(
            SQL_PAR_ARTICLES, {"articles": articles, "collections": collections}
        )
        return [_extrait(ligne) for ligne in lignes.mappings()]

    async def document(self, doc_id: str) -> DocumentTrace | None:
        versions = (
            (
                await self._conn.execute(
                    text(
                        "SELECT collection, version, etat, date_debut, hash_contenu, obsolete, "
                        "ingere_le, url_source FROM document WHERE doc_id = :doc_id "
                        "ORDER BY ingere_le, id"
                    ),
                    {"doc_id": doc_id},
                )
            )
            .mappings()
            .all()
        )
        if not versions:
            return None
        chunks = await self._conn.execute(
            text(
                "SELECT c.id, d.version, c.article, c.ordre, c.texte "
                "FROM chunk c JOIN document d ON d.id = c.document_id "
                "WHERE d.doc_id = :doc_id ORDER BY d.ingere_le, d.id, c.ordre"
            ),
            {"doc_id": doc_id},
        )
        return DocumentTrace(
            doc_id=doc_id,
            collection=versions[-1]["collection"],
            versions=[
                VersionDocument(**{f.name: v[f.name] for f in fields(VersionDocument)})
                for v in versions
            ],
            chunks=[ChunkDocument(c.id, c.version, c.article, c.ordre, c.texte) for c in chunks],
        )

    async def ingestions(self, limit: int, offset: int) -> list[IngestionJournalisee]:
        lignes = await self._conn.execute(
            text(
                "SELECT id, instantane_sha256, recu_le, rapport FROM ingestion "
                "ORDER BY id DESC LIMIT :limit OFFSET :offset"
            ),
            {"limit": limit, "offset": offset},
        )
        return [_ingestion(ligne) for ligne in lignes.mappings()]

    async def ingestion(self, id_: int) -> IngestionJournalisee | None:
        ligne = (
            (
                await self._conn.execute(
                    text(
                        "SELECT id, instantane_sha256, recu_le, rapport FROM ingestion "
                        "WHERE id = :id"
                    ),
                    {"id": id_},
                )
            )
            .mappings()
            .first()
        )
        return None if ligne is None else _ingestion(ligne)

    async def etat(self) -> EtatCorpus:
        ligne = (
            await self._conn.execute(
                text(
                    "SELECT (SELECT instantane_sha256 FROM ingestion ORDER BY id DESC LIMIT 1) "
                    "AS sha, (SELECT count(*) FROM chunk c JOIN document d ON d.id = c.document_id "
                    "WHERE NOT d.obsolete) AS chunks"
                )
            )
        ).one()
        return EtatCorpus(ligne.sha, int(ligne.chunks))
