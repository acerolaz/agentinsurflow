"""Intégration — l'image PostgreSQL annexe (bases, comptes, extension) et les moteurs de rag.

Demande le PostgreSQL du compose (``make test-integration``) et les mots de passe ``PG_*`` de
l'environnement (``.env`` en local, générés à chaque run en CI).
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import URL, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from agentinsurflow_rag.infrastructure.postgres.connexions import ConfigBD, creer_moteurs

# compte → base où il se connecte (version _test)
COMPTES = {
    "migrateur": "vecteurs",
    "writer": "vecteurs",
    "reader": "vecteurs",
    "dossiers": "dossiers",
    "traces_writer": "traces",
    "traces_reader": "traces",
}


def _url(compte: str, base: str) -> URL:
    return URL.create(
        "postgresql+asyncpg",
        username=compte,
        password=os.environ[f"PG_{compte.upper()}_PASSWORD"],
        host=os.environ.get("PG_HOST", "localhost"),
        port=int(os.environ.get("PG_PORT", "5432")),
        database=f"{base}_test",
    )


@pytest.mark.parametrize("compte", COMPTES)
async def test_chaque_compte_se_connecte(compte: str) -> None:
    moteur = create_async_engine(_url(compte, COMPTES[compte]))
    try:
        async with moteur.connect() as conn:
            assert await conn.scalar(text("SELECT current_user")) == compte
    finally:
        await moteur.dispose()


@pytest.mark.parametrize(("compte", "base"), [("reader", "dossiers"), ("dossiers", "vecteurs")])
async def test_compte_refuse_sur_une_base_qui_n_est_pas_la_sienne(compte: str, base: str) -> None:
    moteur = create_async_engine(_url(compte, base))
    try:
        with pytest.raises(DBAPIError, match="permission denied"):
            async with moteur.connect():
                pass
    finally:
        await moteur.dispose()


async def test_moteurs_de_rag_visent_vecteurs_avec_pgvector() -> None:
    moteurs = creer_moteurs(ConfigBD(pg_suffixe_bases="_test"))  # type: ignore[call-arg]
    try:
        for compte, moteur in (("writer", moteurs.writer), ("reader", moteurs.reader)):
            async with moteur.connect() as conn:
                ligne = (await conn.execute(text("SELECT current_user, current_database()"))).one()
                assert tuple(ligne) == (compte, "vecteurs_test")
                extensions = (await conn.scalars(text("SELECT extname FROM pg_extension"))).all()
                assert "vector" in extensions
    finally:
        await moteurs.fermer()
