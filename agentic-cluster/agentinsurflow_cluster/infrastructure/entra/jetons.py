"""Jeton d'application (client credentials) : secret local d'abord, sinon identité managée fédérée.

Même ordre que ``serveur-mcp`` et ``rag`` (copie adaptée : services séparés, pas d'import croisé).
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
    """``None`` si la configuration est incomplète (l'appelant décide de l'échec)."""
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
