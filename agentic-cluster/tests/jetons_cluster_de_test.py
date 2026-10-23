"""Faux tenant Entra du cluster : une clé RSA de test signe les jetons, aucun appel réseau.

Nommé ``jetons_cluster_…`` : d'autres ``jetons_*_de_test.py`` partagent le ``pythonpath`` de pytest.
"""

from __future__ import annotations

import time
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from agentinsurflow_cluster.infrastructure.entra.config import ConfigCluster

TENANT = "00000000-0000-0000-0000-000000000001"
CLIENT_CLUSTER = "33333333-3333-3333-3333-333333333333"
AUDIENCE_CLUSTER = "api://agentic-cluster"
EMETTEUR_V2 = f"https://login.microsoftonline.com/{TENANT}/v2.0"
EMETTEUR_V1 = f"https://sts.windows.net/{TENANT}/"

CLE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
CLE_PUBLIQUE = CLE.public_key()


def creer(
    roles: list[str] | None = None,
    *,
    aud: str = AUDIENCE_CLUSTER,
    iss: str = EMETTEUR_V2,
    oid: str = "oid-gestionnaire-a",
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
    return jwt.encode(revendications, CLE, algorithm="RS256")


def config_cluster() -> ConfigCluster:
    return ConfigCluster(  # type: ignore[call-arg]
        _env_file=None, azure_tenant_id=TENANT, insurflow_cluster_client_id=CLIENT_CLUSTER
    )


class FauxJwks:
    def get_signing_key_from_jwt(self, jeton: str) -> Any:
        return type("Cle", (), {"key": CLE_PUBLIQUE})()
