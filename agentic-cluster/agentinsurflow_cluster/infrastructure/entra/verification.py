"""Validation d'un jeton de gestionnaire (audience ``api://agentinsurflow-cluster`` ou appId du cluster).

Même contrôle que serveur-mcp (RS256, émetteur v1 ou v2, audience, ``exp``, ``oid``) ; copie
adaptée, aucun import entre services.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import jwt

from .config import ConfigCluster

AUDIENCE_PAR_DEFAUT = "api://agentinsurflow-cluster"


class ErreurAuth(Exception):
    """Jeton sans valeur : signature, émetteur, audience, expiration ou identité invalides."""


@dataclass(frozen=True)
class Gestionnaire:
    oid: str
    roles: frozenset[str]
    jeton: str  # transmis aux agents pour l'OBO, jamais journalisé


def audiences(cfg: ConfigCluster) -> list[str]:
    app = cfg.insurflow_cluster_client_id
    return [AUDIENCE_PAR_DEFAUT, *([app, f"api://{app}"] if app else [])]


def emetteurs(cfg: ConfigCluster) -> list[str]:
    tenant = cfg.azure_tenant_id
    return [
        f"https://login.microsoftonline.com/{tenant}/v2.0",
        f"https://sts.windows.net/{tenant}/",
    ]


def url_jwks(cfg: ConfigCluster) -> str:
    return f"https://login.microsoftonline.com/{cfg.azure_tenant_id}/discovery/v2.0/keys"


def verifier_jeton(jeton: str, cle: Any, cfg: ConfigCluster) -> Gestionnaire:
    try:
        revendications = jwt.decode(
            jeton,
            cle,
            algorithms=["RS256"],
            audience=audiences(cfg),
            issuer=emetteurs(cfg),
            options={"require": ["exp", "iss", "aud"]},
        )
    except jwt.PyJWTError as exc:
        raise ErreurAuth(str(exc)) from exc
    oid = revendications.get("oid")
    if not isinstance(oid, str) or not oid:
        raise ErreurAuth("revendication oid absente")
    roles = revendications.get("roles") or []
    return Gestionnaire(oid, frozenset(str(r) for r in roles), jeton)
