"""Jeton On-Behalf-Of : le serveur MCP échange le jeton du gestionnaire contre un jeton pour rag
ou underwriting-admin (permission déléguée ``access_as_user``).

Sans secret en Azure : assertion tirée de l'identité managée attribuée par l'utilisateur, déclarée
comme identifiant fédéré. En local seulement : ``MCP_CLIENT_SECRET``.
"""

from __future__ import annotations

from typing import Any, Literal

from azure.core.exceptions import AzureError
from azure.identity import ManagedIdentityCredential, OnBehalfOfCredential
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from starlette.concurrency import run_in_threadpool

from ...domain.models import DOSSIERS_INDISPONIBLES, Appelant, ErreurOutil
from ..otel.telemetrie import echec, tracer
from .application import PORTEE_FEDERATION


class ConfigObo(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    azure_tenant_id: str
    mcp_api_client_id: str
    rag_api_client_id: str
    underwriting_api_client_id: str
    gateway_url: str = "http://localhost:8000"  # D22 : tout passe par la gateway
    mcp_client_secret: SecretStr | None = None  # 🔒 .env local seulement
    azure_uami_client_id: str | None = None  # identité managée (Azure)


def _jeton_obo(cfg: ConfigObo, jeton_utilisateur: str, client_cible: str) -> str:
    """Synchrone (SDK azure-identity) : appelé hors de la boucle d'événements."""
    secret = cfg.mcp_client_secret.get_secret_value() if cfg.mcp_client_secret else ""
    assertion: dict[str, Any]
    if secret:
        assertion = {"client_secret": secret}
    elif cfg.azure_uami_client_id:
        identite = ManagedIdentityCredential(client_id=cfg.azure_uami_client_id)
        assertion = {"client_assertion_func": lambda: identite.get_token(PORTEE_FEDERATION).token}
    else:
        raise ErreurOutil(DOSSIERS_INDISPONIBLES, "OBO non configuré (secret ou identité)")
    credential = OnBehalfOfCredential(
        cfg.azure_tenant_id, cfg.mcp_api_client_id, user_assertion=jeton_utilisateur, **assertion
    )
    try:
        return credential.get_token(f"api://{client_cible}/access_as_user").token
    except AzureError as exc:
        raise ErreurOutil(DOSSIERS_INDISPONIBLES, "Jeton On-Behalf-Of refusé") from exc


class JetonsEntra:
    """Port ``JetonsPort`` ; ``cfg`` est ``None`` si l'Entra n'est pas configuré (OBO refusé)."""

    def __init__(self, cfg: ConfigObo | None) -> None:
        self._cfg = cfg

    async def obo(self, appelant: Appelant, cible: Literal["rag", "underwriting"]) -> str:
        with tracer.start_as_current_span(
            "obo.echanger",
            attributes={"obo.cible": cible, "obo.reussi": False},
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            if self._cfg is None:
                echec(span, "OBO non configuré")
                raise ErreurOutil(
                    DOSSIERS_INDISPONIBLES, "OBO non configuré (config Entra absente)"
                )
            client = (
                self._cfg.rag_api_client_id
                if cible == "rag"
                else self._cfg.underwriting_api_client_id
            )
            try:
                jeton = await run_in_threadpool(_jeton_obo, self._cfg, appelant.jeton, client)
            except Exception:
                echec(span, "OBO refusé")
                raise
            span.set_attribute("obo.reussi", True)
            return jeton
