"""Alembic, base ``vecteurs`` : migrations écrites à la main (SQL), sans autogénération ni ORM."""

from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from agentinsurflow_rag.infrastructure.postgres.connexions import ConfigBD


def _url() -> str:
    # les tests passent l'URL de la base _test ; sinon le compte migrateur de l'environnement
    return context.config.get_main_option("sqlalchemy.url") or ConfigBD().url("migrateur")  # type: ignore[call-arg]


def _migrer(conn: Connection) -> None:
    context.configure(connection=conn, target_metadata=None)
    with context.begin_transaction():
        context.run_migrations()


async def _en_ligne() -> None:
    moteur = create_async_engine(_url(), poolclass=pool.NullPool)
    async with moteur.connect() as conn:
        await conn.run_sync(_migrer)
    await moteur.dispose()


if context.is_offline_mode():
    raise RuntimeError("mode hors ligne non pris en charge : lancer alembic sur une base joignable")
asyncio.run(_en_ligne())
