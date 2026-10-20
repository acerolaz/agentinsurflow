"""Date d'extraction de chaque version d'article (attribution Etalab 2.0, spec §4.3).

``extrait_le`` : jour de l'instantané Légifrance d'où vient la version. Les lignes existantes
reprennent le jour de leur ingestion, faute de mieux.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE document ADD COLUMN extrait_le date")
    op.execute("UPDATE document SET extrait_le = ingere_le::date")
    op.execute("ALTER TABLE document ALTER COLUMN extrait_le SET NOT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE document DROP COLUMN extrait_le")
