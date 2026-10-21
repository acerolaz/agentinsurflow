"""Faux tenant Entra : une clé RSA de test signe les jetons ; aucun appel réseau à Entra.

Nommé ``jetons_mcp_…`` : ``rag/tests/jetons_de_test.py`` est sur le même ``pythonpath`` de pytest.
"""

from __future__ import annotations

import time
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from agentinsurflow_mcp.infrastructure.entra.jetons import ConfigAuth

TENANT = "00000000-0000-0000-0000-000000000001"
CLIENT_ID = "22222222-2222-2222-2222-222222222222"
CLIENT_RAG = "11111111-1111-1111-1111-111111111111"
AZP_ORCHESTRATEUR = "aaaaaaaa-0000-0000-0000-000000000001"
AZP_REDACTEUR = "aaaaaaaa-0000-0000-0000-000000000002"
AZP_ACTUAIRE = "aaaaaaaa-0000-0000-0000-000000000003"
EMETTEUR_V2 = f"https://login.microsoftonline.com/{TENANT}/v2.0"
EMETTEUR_V1 = f"https://sts.windows.net/{TENANT}/"

CLE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
CLE_PUBLIQUE = CLE.public_key()


def creer(
    azp: str | None = AZP_REDACTEUR,
    roles: list[str] | None = None,
    *,
    azp_v1: bool = False,
    oid: str = "oid-gestionnaire-a",
    aud: str = CLIENT_ID,
    iss: str = EMETTEUR_V2,
    expire_dans: int = 300,
) -> str:
    maintenant = int(time.time())
    revendications: dict[str, Any] = {
        "aud": aud,
        "iss": iss,
        "oid": oid,
        "roles": roles if roles is not None else ["Gestionnaire"],
        "iat": maintenant - 60,
        "nbf": maintenant - 60,
        "exp": maintenant + expire_dans,
    }
    if azp is not None:
        revendications["appid" if azp_v1 else "azp"] = azp
    return jwt.encode(revendications, CLE, algorithm="RS256")


def config_auth() -> ConfigAuth:
    """La configuration Entra du faux tenant (aucun ``.env`` lu)."""
    return ConfigAuth(  # type: ignore[call-arg]
        _env_file=None,
        azure_tenant_id=TENANT,
        mcp_api_client_id=CLIENT_ID,
        mcp_azp_orchestrateur=AZP_ORCHESTRATEUR,
        mcp_azp_redacteur=AZP_REDACTEUR,
        mcp_azp_actuaire=AZP_ACTUAIRE,
    )
