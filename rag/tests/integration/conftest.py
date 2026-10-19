"""Fixtures des TI qui touchent PostgreSQL : base ``vecteurs_test`` migrée une fois par session,
une transaction annulée par test (les tests ne s'influencent pas).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from agentinsurflow_rag.infrastructure.postgres.connexions import ConfigBD

RAG = Path(__file__).resolve().parents[2]


def config_bd() -> ConfigBD:
    return ConfigBD(pg_suffixe_bases="_test")  # type: ignore[call-arg]


def config_alembic() -> Config:
    cfg = Config(str(RAG / "alembic.ini"), ini_section="vecteurs")
    cfg.set_main_option("sqlalchemy.url", config_bd().url("migrateur"))
    return cfg


@pytest.fixture(scope="session")
def vecteurs_migree() -> Iterator[None]:
    """La base ``vecteurs_test`` au dernier schéma ; repart de zéro à chaque session."""
    cfg = config_alembic()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield


async def _connexion(moteur: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    async with moteur.connect() as conn:
        transaction = await conn.begin()
        try:
            yield conn
        finally:
            await transaction.rollback()
    await moteur.dispose()


@pytest.fixture
async def conn_writer(vecteurs_migree: None) -> AsyncIterator[AsyncConnection]:
    async for conn in _connexion(create_async_engine(config_bd().url("writer"))):
        yield conn


@pytest.fixture
async def conn_reader(vecteurs_migree: None) -> AsyncIterator[AsyncConnection]:
    async for conn in _connexion(create_async_engine(config_bd().url("reader"))):
        yield conn
