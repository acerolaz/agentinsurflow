"""Faux tenant Entra : une clé RSA de test signe les jetons ; aucun appel réseau à Entra."""

from __future__ import annotations

import time
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from agentinsurflow_rag.infrastructure.entra.jetons import ConfigAuth

TENANT = "00000000-0000-0000-0000-000000000001"
CLIENT_ID = "11111111-1111-1111-1111-111111111111"
EMETTEUR_V2 = f"https://login.microsoftonline.com/{TENANT}/v2.0"
EMETTEUR_V1 = f"https://sts.windows.net/{TENANT}/"

CLE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
CLE_PUBLIQUE = CLE.public_key()
CLE_ETRANGERE = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def creer(
    roles: list[str] | None = None,
    *,
    oid: str = "oid-gestionnaire-a",
    aud: str = CLIENT_ID,
    iss: str = EMETTEUR_V2,
    expire_dans: int = 300,
    cle: Any = CLE,
    **autres: Any,
) -> str:
    maintenant = int(time.time())
    revendications = {
        "aud": aud,
        "iss": iss,
        "oid": oid,
        "roles": roles if roles is not None else ["Gestionnaire"],
        "iat": maintenant - 60,
        "nbf": maintenant - 60,
        "exp": maintenant + expire_dans,
    } | autres
    return jwt.encode(revendications, cle, algorithm="RS256")


def config_auth() -> ConfigAuth:
    """La configuration Entra du faux tenant (aucun ``.env`` lu)."""
    return ConfigAuth(_env_file=None, azure_tenant_id=TENANT, rag_api_client_id=CLIENT_ID)  # type: ignore[call-arg]
