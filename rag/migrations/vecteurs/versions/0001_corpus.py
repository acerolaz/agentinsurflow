"""Corpus : document (une version d'un article), chunk (unité de recherche et de citation),
ingestion (rapports) ; index HNSW, GIN et B-tree ; droits writer et reader (spec §2.1).

L'extension vector est créée par l'image annexe (superutilisateur), pas ici.

Revision ID: 0001
Revises:
"""

from __future__ import annotations

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE document (
            id bigserial PRIMARY KEY,
            doc_id text NOT NULL,
            collection text NOT NULL CHECK (collection IN (
                'textes_reglementaires', 'procedures_internes', 'cgv_conditions', 'notices_produits'
            )),
            version text NOT NULL,
            date_debut date,
            etat text NOT NULL,
            url_source text NOT NULL,
            hash_contenu char(64) NOT NULL,
            obsolete boolean NOT NULL DEFAULT false,
            ingere_le timestamptz NOT NULL DEFAULT now(),
            UNIQUE (doc_id, version)
        )
        """
    )
    op.execute(
        "CREATE INDEX document_collection_courante ON document (collection) WHERE NOT obsolete"
    )
    op.execute(
        """
        CREATE TABLE chunk (
            id bigserial PRIMARY KEY,
            document_id bigint NOT NULL REFERENCES document (id) ON DELETE CASCADE,
            article text NOT NULL,
            regle_id text,
            ordre int NOT NULL,
            texte text NOT NULL,
            embedding vector(1536) NOT NULL,
            tsv tsvector GENERATED ALWAYS AS (to_tsvector('french', article || ' ' || texte)) STORED
        )
        """
    )
    op.execute(
        "CREATE INDEX chunk_embedding_hnsw ON chunk USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute("CREATE INDEX chunk_tsv_gin ON chunk USING gin (tsv)")
    op.execute("CREATE INDEX chunk_article ON chunk (article)")
    op.execute("CREATE INDEX chunk_document ON chunk (document_id)")
    op.execute(
        """
        CREATE TABLE ingestion (
            id bigserial PRIMARY KEY,
            instantane_sha256 char(64) NOT NULL,
            recu_le timestamptz NOT NULL DEFAULT now(),
            rapport jsonb NOT NULL
        )
        """
    )
    # writer : ingestion (lit, insère, marque obsolète) ; reader : recherche, lecture seule
    op.execute("GRANT SELECT, INSERT, UPDATE ON document, chunk, ingestion TO writer")
    op.execute("GRANT USAGE ON SEQUENCE document_id_seq, chunk_id_seq, ingestion_id_seq TO writer")
    op.execute("GRANT SELECT ON document, chunk, ingestion TO reader")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS chunk, document, ingestion")
