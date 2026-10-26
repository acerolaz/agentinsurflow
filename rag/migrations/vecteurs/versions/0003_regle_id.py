"""Règle du barème fondée par un document (procédures internes, #98).

``regle_id`` : facultatif, ``NULL`` pour les textes Légifrance ; renvoyé dans la citation des
extraits pour que le garde-fou GF5 du cluster retrouve la source d'un refus.

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE document ADD COLUMN regle_id text")


def downgrade() -> None:
    op.execute("ALTER TABLE document DROP COLUMN regle_id")
