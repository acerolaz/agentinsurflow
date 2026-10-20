"""Câblage des adaptateurs par ``Depends`` : connexions (une transaction par requête),
embeddings et réglages de la recherche. Rien n'est global : tout est lu ou créé à la demande,
ou au démarrage dans ``app.state``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Request
from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from ..domain.ports import ClientEmbeddings
from ..infrastructure.azure_openai.config import charger_config
from ..infrastructure.azure_openai.embeddings import fabrique_embeddings
from .erreurs import ErreurApi


class ConfigRag(BaseSettings):
    """``RAG_SEUIL`` n'a pas de défaut : la valeur se calibre (``make calibrer``, C1)."""

    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    rag_seuil: float = Field(ge=0, le=1)
    rag_top_k: int = Field(default=5, ge=1, le=20)
    rag_candidats: int = Field(default=20, ge=1, le=200)


def charger_rag() -> ConfigRag:
    try:
        return ConfigRag()  # type: ignore[call-arg]
    except ValidationError as exc:
        raise ErreurApi(503, "CONFIGURATION_INCOMPLETE", "RAG_SEUIL manquant ou invalide") from exc


@asynccontextmanager
async def ouvrir(request: Request, compte: str) -> AsyncIterator[AsyncConnection]:
    """Une transaction par requête : validée en fin de requête, annulée sur exception.
    Base non configurée ou injoignable → 503 ``BASE_INDISPONIBLE`` (jamais une 500)."""
    moteurs = getattr(request.app.state, "moteurs", None)
    if moteurs is None:
        raise ErreurApi(503, "BASE_INDISPONIBLE", "Base de données non configurée")
    moteur: AsyncEngine = getattr(moteurs, compte)
    try:
        conn = await moteur.connect()
    except (OSError, DBAPIError) as exc:
        raise ErreurApi(503, "BASE_INDISPONIBLE", "Base de données injoignable") from exc
    try:
        async with conn.begin():
            yield conn
    finally:
        await conn.close()


async def connexion_writer(request: Request) -> AsyncIterator[AsyncConnection]:
    """Compte ``writer`` (ingestion)."""
    async with ouvrir(request, "writer") as conn:
        yield conn


async def connexion_reader(request: Request) -> AsyncIterator[AsyncConnection]:
    """Compte ``reader`` (recherche, consultation) : lecture seule."""
    async with ouvrir(request, "reader") as conn:
        yield conn


def obtenir_embeddings() -> ClientEmbeddings:
    emb = fabrique_embeddings(charger_config())
    if emb is None:
        raise ErreurApi(503, "EMBEDDINGS_INDISPONIBLES", "Modèle d'embeddings non configuré")
    return emb
