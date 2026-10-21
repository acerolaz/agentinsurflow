"""Application HTTP du serveur MCP : ``/health`` et ``/mcp`` (Streamable HTTP, port 8003)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version

from fastapi import FastAPI
from jwt import PyJWKClient
from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from ..infrastructure.entra.jetons import ConfigAuth
from .securite import GardeMcp
from .serveur import ServeurMcp

journal = logging.getLogger(__name__)

VERSION = version("agentinsurflow-mcp")


class ConfigApp(BaseSettings):
    """Versions gravées dans l'image au build : SHA du commit, release vX.Y.Z, manifeste."""

    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    app_version: str = "dev"
    app_release: str = "dev"
    app_manifeste: str = "dev"
    app_env: str = "local"


def creer_app(serveur: ServeurMcp) -> FastAPI:
    @asynccontextmanager
    async def cycle_de_vie(app: FastAPI) -> AsyncIterator[None]:
        # ponytail: sans configuration Entra l'API démarre quand même, /mcp répond 503
        if app.state.config_auth is None:  # déjà posée : tests
            try:
                app.state.config_auth = ConfigAuth()  # type: ignore[call-arg]
                app.state.jwks = PyJWKClient(app.state.config_auth.url_jwks, cache_keys=True)
            except ValidationError:
                journal.warning("Entra non configuré (AZURE_TENANT_ID, MCP_API_CLIENT_ID) : 503")
        async with serveur.session_manager.run():
            yield

    app = FastAPI(title="AgentInsurFlow — serveur MCP", version=VERSION, lifespan=cycle_de_vie)
    app.state.config_auth = None
    app.state.jwks = None

    @app.get("/health")
    async def sante() -> dict[str, str]:
        """Sonde : toujours 200, versions gravées au build."""
        cfg = ConfigApp()
        return {
            "version": cfg.app_version,
            "release": cfg.app_release,
            "manifeste": cfg.app_manifeste,
            "environnement": cfg.app_env,
        }

    app.mount("/", serveur.streamable_http_app())  # la route du SDK est /mcp
    app.add_middleware(GardeMcp)
    return app


app = creer_app(ServeurMcp())
