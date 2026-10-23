"""Source d'assertion unique des applications Entra : secret local d'abord, sinon identité
managée fédérée (sans secret en Azure). Utilisée par l'OBO et par le jeton LLM.

Même ordre que ``serveur-mcp`` et ``rag`` (copie adaptée : services séparés, pas d'import croisé).
"""

from __future__ import annotations

from typing import Any

from azure.identity import (
    ClientAssertionCredential,
    ClientSecretCredential,
    ManagedIdentityCredential,
)

from .config import ConfigCluster

PORTEE_FEDERATION = "api://AzureADTokenExchange/.default"


def source_assertion(cfg: ConfigCluster) -> dict[str, Any] | None:
    """``{"client_secret"}`` ou ``{"client_assertion_func"}`` ; ``None`` si rien n'est configuré.

    L'identité managée n'est créée qu'ici : l'appelant mémorise le résultat.
    """
    secret = cfg.insurflow_client_secret
    if secret and secret.get_secret_value():
        return {"client_secret": secret.get_secret_value()}
    if cfg.azure_uami_client_id:
        identite = ManagedIdentityCredential(client_id=cfg.azure_uami_client_id)
        return {"client_assertion_func": lambda: identite.get_token(PORTEE_FEDERATION).token}
    return None


def credential_application(
    tenant: str, client_id: str, assertion: dict[str, Any]
) -> ClientSecretCredential | ClientAssertionCredential:
    if "client_secret" in assertion:
        return ClientSecretCredential(tenant, client_id, assertion["client_secret"])
    return ClientAssertionCredential(tenant, client_id, assertion["client_assertion_func"])
