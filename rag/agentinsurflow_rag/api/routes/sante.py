from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic_settings import BaseSettings, SettingsConfigDict

from ..schemas.sante import Sante

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


@router.get("/health")
def sante(cfg: Annotated[ConfigApp, Depends(charger_app)]) -> Sante:
    return Sante(
        version=cfg.app_version,
        release=cfg.app_release,
        manifeste=cfg.app_manifeste,
        environnement=cfg.app_env,
    )
