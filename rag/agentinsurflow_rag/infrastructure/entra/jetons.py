"""Validation d'un jeton Entra ID pour l'API rag (audience ``agentinsurflow-rag``).

Signature RS256 (clé du tenant), émetteur v1 ou v2 du tenant, audience (ID client ou
``api://<ID client>``), expiration exigée, ``oid`` exigé. La gateway a déjà contrôlé le jeton :
ceci est la seconde barrière (défense en profondeur, S3-25).
"""

from __future__ import annotations

from typing import Any

import jwt
from pydantic_settings import BaseSettings, SettingsConfigDict

from ...domain.models import Appelant


class ConfigAuth(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    azure_tenant_id: str
    rag_api_client_id: str

    @property
    def audiences(self) -> list[str]:
        return [self.rag_api_client_id, f"api://{self.rag_api_client_id}"]

    @property
    def emetteurs(self) -> list[str]:
        tenant = self.azure_tenant_id
        return [
            f"https://login.microsoftonline.com/{tenant}/v2.0",
            f"https://sts.windows.net/{tenant}/",
        ]

    @property
    def url_jwks(self) -> str:
        return f"https://login.microsoftonline.com/{self.azure_tenant_id}/discovery/v2.0/keys"


class ErreurAuth(Exception):
    """Jeton absent de valeur : signature, émetteur, audience, expiration ou identité invalides."""


def verifier_jeton(jeton: str, cle: Any, cfg: ConfigAuth) -> Appelant:
    try:
        revendications = jwt.decode(
            jeton,
            cle,
            algorithms=["RS256"],
            audience=cfg.audiences,
            issuer=cfg.emetteurs,
            options={"require": ["exp", "iss", "aud"]},
        )
    except jwt.PyJWTError as exc:
        raise ErreurAuth(str(exc)) from exc
    oid = revendications.get("oid")
    if not isinstance(oid, str) or not oid:
        raise ErreurAuth("revendication oid absente")
    roles = revendications.get("roles") or []
    return Appelant(oid=oid, roles=frozenset(str(r) for r in roles))
