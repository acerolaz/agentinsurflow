"""Intégration — migrations Alembic de la base ``vecteurs`` (schéma, index, droits)."""

from __future__ import annotations

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncConnection

from conftest import config_alembic

INSERT_DOCUMENT = text(
    "INSERT INTO document (doc_id, collection, version, etat, url_source, hash_contenu) "
    "VALUES (:doc_id, 'textes_reglementaires', :version, 'VIGUEUR', 'https://x', :hash) "
    "RETURNING id"
)


async def _document(
    conn: AsyncConnection, doc_id: str = "LEGIARTI0001", version: str = "v1"
) -> int:
    resultat = await conn.execute(
        INSERT_DOCUMENT, {"doc_id": doc_id, "version": version, "hash": "a" * 64}
    )
    return int(resultat.scalar_one())


async def test_upgrade_head_cree_les_tables_et_index(conn_reader: AsyncConnection) -> None:
    tables = set(
        (
            await conn_reader.scalars(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
        ).all()
    )
    assert {"document", "chunk", "ingestion"} <= tables
    index = (
        await conn_reader.scalars(text("SELECT indexdef FROM pg_indexes WHERE tablename = 'chunk'"))
    ).all()
    definitions = " ".join(index)
    assert "USING hnsw (embedding vector_cosine_ops)" in definitions
    assert "USING gin (tsv)" in definitions
    assert "(article)" in definitions


async def test_index_partiel_sur_les_versions_courantes(conn_reader: AsyncConnection) -> None:
    index = (
        await conn_reader.scalars(
            text("SELECT indexdef FROM pg_indexes WHERE tablename = 'document'")
        )
    ).all()
    assert any("(collection)" in d and "WHERE (NOT obsolete)" in d for d in index)


async def test_writer_ecrit_et_reader_lit(conn_writer: AsyncConnection) -> None:
    document_id = await _document(conn_writer)
    assert document_id > 0


async def test_reader_ne_peut_pas_ecrire(conn_reader: AsyncConnection) -> None:
    with pytest.raises(ProgrammingError, match="permission denied"):
        await _document(conn_reader)


async def test_doc_id_version_unique(conn_writer: AsyncConnection) -> None:
    await _document(conn_writer)
    with pytest.raises(IntegrityError):
        await _document(conn_writer)


async def test_une_seule_version_courante_par_doc_id(conn_writer: AsyncConnection) -> None:
    await _document(conn_writer, version="v1")
    with pytest.raises(IntegrityError):
        await _document(conn_writer, version="v2")  # v1 n'est pas marquée obsolète


async def test_pas_de_colonne_regle_id(conn_reader: AsyncConnection) -> None:
    colonnes = (
        await conn_reader.scalars(
            text("SELECT column_name FROM information_schema.columns WHERE table_name = 'chunk'")
        )
    ).all()
    assert "regle_id" not in colonnes


async def test_collection_hors_liste_refusee(conn_writer: AsyncConnection) -> None:
    with pytest.raises(IntegrityError):
        await conn_writer.execute(
            text(
                "INSERT INTO document (doc_id, collection, version, etat, url_source, hash_contenu)"
                " VALUES ('X', 'inconnue', 'v1', 'VIGUEUR', 'https://x', :h)"
            ),
            {"h": "a" * 64},
        )


async def test_tsv_genere_contient_le_numero(conn_writer: AsyncConnection) -> None:
    document_id = await _document(conn_writer)
    await conn_writer.execute(
        text(
            "INSERT INTO chunk (document_id, article, ordre, texte, embedding) "
            "VALUES (:d, 'L211-1', 0, 'Toute personne physique ou morale', :e)"
        ),
        {"d": document_id, "e": "[" + ",".join(["0.1"] * 1536) + "]"},
    )
    trouve = await conn_writer.scalar(
        text("SELECT count(*) FROM chunk WHERE tsv @@ websearch_to_tsquery('french', 'L211-1')")
    )
    assert trouve == 1


def test_downgrade_puis_upgrade_sans_erreur(vecteurs_migree: None) -> None:
    cfg = config_alembic()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
