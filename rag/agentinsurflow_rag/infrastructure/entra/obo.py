"""Jeton On-Behalf-Of : rag échange le jeton du gestionnaire contre un jeton pour
underwriting-admin (permission déléguée ``access_as_user``, S3-20).

rag prouve son identité sans secret en Azure : assertion tirée de l'identité managée attribuée
par l'utilisateur, déclarée comme identifiant fédéré. En local seulement : ``RAG_CLIENT_SECRET``.
"""

from __future__ import annotations

import logging
from typing import Any

from azure.core.exceptions import AzureError
from azure.identity import ManagedIdentityCredential, OnBehalfOfCredential
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from ...domain.ports import ErreurDossiers

PORTEE_FEDERATION = "api://AzureADTokenExchange/.default"
logger = logging.getLogger(__name__)


class ConfigObo(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    azure_tenant_id: str
    rag_api_client_id: str
    underwriting_api_client_id: str
    # D22 : dossiers lus par la gateway (rôle par route, débit), jamais en direct
    underwriting_url: str = "http://localhost:8000"
    rag_client_secret: SecretStr | None = None  # 🔒 .env local seulement
    azure_uami_client_id: str | None = None  # identité managée (Azure)


def jeton_obo(cfg: ConfigObo, jeton_utilisateur: str) -> str:
    """Synchrone (SDK azure-identity) : l'appelant le lance hors de la boucle d'événements."""
    secret = cfg.rag_client_secret.get_secret_value() if cfg.rag_client_secret else ""
    assertion: dict[str, Any]
    if secret:
        assertion = {"client_secret": secret}
    elif cfg.azure_uami_client_id:
        identite = ManagedIdentityCredential(client_id=cfg.azure_uami_client_id)
        assertion = {"client_assertion_func": lambda: identite.get_token(PORTEE_FEDERATION).token}
    else:
        raise ErreurDossiers("ni RAG_CLIENT_SECRET (local) ni AZURE_UAMI_CLIENT_ID (Azure)")
    credential = OnBehalfOfCredential(
        cfg.azure_tenant_id, cfg.rag_api_client_id, user_assertion=jeton_utilisateur, **assertion
    )
    try:
        return credential.get_token(f"api://{cfg.underwriting_api_client_id}/access_as_user").token
    except AzureError as exc:
        # #47 : code AADSTS et identifiants de corrélation d'Entra ; jamais le jeton
        logger.warning("jeton On-Behalf-Of refusé par Entra : %s", exc)
        raise ErreurDossiers(f"jeton On-Behalf-Of refusé : {exc!r}") from exc
