"""Fixtures des TI qui touchent PostgreSQL : base ``vecteurs_test`` migrée une fois par session,
une transaction annulée par test (les tests ne s'influencent pas).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from agentinsurflow_rag.api import app
from agentinsurflow_rag.api.dependances import (
    ConfigRag,
    charger_rag,
    connexion_reader,
    connexion_writer,
    obtenir_embeddings,
)
from agentinsurflow_rag.api.securite import charger_auth, obtenir_cle
from agentinsurflow_rag.infrastructure.entra.jetons import ConfigAuth
from agentinsurflow_rag.infrastructure.postgres.connexions import ConfigBD
from corpus_de_test import CORPUS, SHA
from fakes import FakeEmbeddings
from jetons_de_test import CLE_PUBLIQUE, CLIENT_ID, TENANT, creer

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


# ---------------------------------------------------------------- l'API rag en mémoire


def remplacer_dependances(conn: AsyncConnection) -> None:
    """Seules les dépendances externes sont remplacées : base de test, embeddings, clé du tenant.

    Une seule connexion (writer) sert aussi aux lectures : le reader ne verrait pas les lignes
    de la transaction du test, qui n'est jamais validée.
    """

    async def _connexion() -> AsyncIterator[AsyncConnection]:
        yield conn

    app.dependency_overrides.update(
        {
            connexion_writer: _connexion,
            connexion_reader: _connexion,
            obtenir_embeddings: lambda: FakeEmbeddings(),
            charger_rag: lambda: ConfigRag(_env_file=None, rag_seuil=0.4),  # type: ignore[call-arg]
            obtenir_cle: lambda: CLE_PUBLIQUE,
            charger_auth: lambda: ConfigAuth(
                _env_file=None,  # type: ignore[call-arg]
                azure_tenant_id=TENANT,
                rag_api_client_id=CLIENT_ID,
            ),
        }
    )


@pytest.fixture
async def api(conn_writer: AsyncConnection) -> AsyncIterator[httpx.AsyncClient]:
    remplacer_dependances(conn_writer)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://rag"
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def entetes(*roles: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {creer(list(roles))}"}


@pytest.fixture
async def corpus(api: httpx.AsyncClient) -> httpx.AsyncClient:
    """L'API, avec le corpus de fixture (4 articles) ingéré par la vraie route."""
    corps = {"collection": "textes_reglementaires", "instantane_sha256": SHA, "articles": CORPUS}
    reponse = await api.post("/api/ingestions", json=corps, headers=entetes("Ingestion"))
    assert reponse.status_code == 201
    return api


# ---------------------------------------------------------------- traces en mémoire

_EXPORTATEUR = InMemorySpanExporter()


@pytest.fixture(scope="session", autouse=True)
def _fournisseur_de_traces() -> None:
    """Le SDK OTel, une fois par processus (convention du SDK), avec un exportateur en mémoire."""
    fournisseur = TracerProvider(resource=Resource.create({"service.name": "agentinsurflow-rag"}))
    fournisseur.add_span_processor(SimpleSpanProcessor(_EXPORTATEUR))
    trace.set_tracer_provider(fournisseur)


@pytest.fixture
def spans() -> Iterator[InMemorySpanExporter]:
    _EXPORTATEUR.clear()
    yield _EXPORTATEUR
    _EXPORTATEUR.clear()
