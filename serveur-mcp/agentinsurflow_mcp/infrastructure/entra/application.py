"""Jeton d'application (client credentials) du serveur MCP : calcul et télémétrie via la gateway.

Même ordre que l'OBO : ``MCP_CLIENT_SECRET`` local d'abord, puis assertion fédérée tirée de
l'identité managée (Azure, sans secret).
"""

from __future__ import annotations

from azure.identity import (
    ClientAssertionCredential,
    ClientSecretCredential,
    ManagedIdentityCredential,
)

PORTEE_FEDERATION = "api://AzureADTokenExchange/.default"


def credential_application(
    tenant: str | None, client_id: str | None, secret: str | None, uami: str | None
) -> ClientSecretCredential | ClientAssertionCredential | None:
    """``None`` si la configuration Entra est incomplète (l'appelant décide de l'échec)."""
    if not (tenant and client_id):
        return None
    if secret:
        return ClientSecretCredential(tenant, client_id, secret)
    if not uami:
        return None
    identite = ManagedIdentityCredential(client_id=uami)
    return ClientAssertionCredential(
        tenant, client_id, lambda: identite.get_token(PORTEE_FEDERATION).token
    )
