from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.exc import DBAPIError

from ...application.use_cases.consulter import etat_du_corpus
from ...infrastructure.postgres.corpus import PgDepotCorpus
from ..dependances import ouvrir
from ..erreurs import ErreurApi
from ..schemas.sante import CorpusSante, Sante

router = APIRouter()


class ConfigApp(BaseSettings):
    """Versions gravées dans l'image au build : SHA du commit, release vX.Y.Z, manifeste."""

    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    app_version: str = "dev"
    app_release: str = "dev"
    app_manifeste: str = "dev"
    app_env: str = "local"


def charger_app() -> ConfigApp:
    return ConfigApp()


async def _corpus(request: Request) -> CorpusSante | None:
    try:
        async with ouvrir(request, "reader") as conn:
            return CorpusSante.model_validate(await etat_du_corpus(PgDepotCorpus(conn)))
    except (ErreurApi, DBAPIError):  # base non configurée, injoignable ou pas encore migrée
        return None


@router.get("/health")
async def sante(request: Request, cfg: Annotated[ConfigApp, Depends(charger_app)]) -> Sante:
    """Sonde : toujours 200 ; ``corpus`` dit si l'ingestion a eu lieu (null sans base)."""
    return Sante(
        version=cfg.app_version,
        release=cfg.app_release,
        manifeste=cfg.app_manifeste,
        environnement=cfg.app_env,
        corpus=await _corpus(request),
    )
