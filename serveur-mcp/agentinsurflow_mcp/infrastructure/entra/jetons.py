"""Validation d'un jeton Entra ID pour le serveur MCP (audience ``agentinsurflow-mcp``).

Mêmes contrôles que rag (RS256, émetteur v1 ou v2, audience, ``exp``, ``oid``), plus l'identité de
l'agent : l'``azp`` (``appid`` pour un jeton v1) est cherché dans les trois variables d'agent.
"""

from __future__ import annotations

from typing import Any

import jwt
from pydantic_settings import BaseSettings, SettingsConfigDict

from ...domain.models import Agent, Appelant


class ConfigAuth(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    azure_tenant_id: str
    mcp_api_client_id: str
    # « a, b » : la même variable que la gateway, une seule liste
    mcp_api_audiences: str = ""
    # ID client des inscriptions d'agent ; vide = agent non reconnu
    mcp_azp_orchestrateur: str = ""
    mcp_azp_redacteur: str = ""
    mcp_azp_actuaire: str = ""

    @property
    def audiences(self) -> list[str]:
        liste = [a.strip() for a in self.mcp_api_audiences.split(",") if a.strip()]
        return liste or [self.mcp_api_client_id, f"api://{self.mcp_api_client_id}"]

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

    def agent_de(self, azp: str) -> Agent | None:
        agents: dict[str, Agent] = {
            self.mcp_azp_orchestrateur: "orchestrateur",
            self.mcp_azp_redacteur: "redacteur",
            self.mcp_azp_actuaire: "actuaire",
        }
        return agents.get(azp) if azp else None


class ErreurAuth(Exception):
    """Jeton sans valeur : signature, émetteur, audience, expiration ou identité invalides."""


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
    azp = str(revendications.get("azp") or revendications.get("appid") or "")
    roles = revendications.get("roles") or []
    return Appelant(
        oid=oid,
        azp=azp,
        agent=cfg.agent_de(azp),
        roles=frozenset(str(r) for r in roles),
        jeton=jeton,
    )
