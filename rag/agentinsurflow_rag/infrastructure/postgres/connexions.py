"""Connexions de rag à PostgreSQL : rag ne connaît que la base ``vecteurs``.

Deux comptes, ``writer`` (ingestion) et ``reader`` (recherche). Les bases ``dossiers`` et
``traces`` appartiennent à underwriting-admin (S3-17).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

Compte = Literal["writer", "reader"]


class ConfigBD(BaseSettings):
    """Mots de passe lus dans l'environnement (secrets de la Container App, ``.env`` en local)."""

    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    pg_host: str = "localhost"
    pg_port: int = 5432
    pg_suffixe_bases: str = ""  # "_test" pour les tests d'intégration
    pg_writer_password: SecretStr
    pg_reader_password: SecretStr

    def url(self, compte: Compte) -> str:
        mot_de_passe = {"writer": self.pg_writer_password, "reader": self.pg_reader_password}
        return URL.create(
            "postgresql+asyncpg",
            username=compte,
            password=mot_de_passe[compte].get_secret_value(),
            host=self.pg_host,
            port=self.pg_port,
            database=f"vecteurs{self.pg_suffixe_bases}",
        ).render_as_string(hide_password=False)


@dataclass(frozen=True)
class Moteurs:
    writer: AsyncEngine
    reader: AsyncEngine

    async def fermer(self) -> None:
        await self.writer.dispose()
        await self.reader.dispose()


def creer_moteurs(cfg: ConfigBD) -> Moteurs:
    """Aucune connexion n'est ouverte ici : le pool se remplit au premier usage."""
    return Moteurs(
        writer=create_async_engine(cfg.url("writer"), pool_pre_ping=True),
        reader=create_async_engine(cfg.url("reader"), pool_pre_ping=True),
    )
