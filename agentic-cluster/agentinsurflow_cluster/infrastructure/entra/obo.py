"""Jetons par agent : OBO en deux sauts vers le MCP, jeton d'application vers le LLM.

Saut 1 : l'application ``agentic-cluster`` échange le jeton du gestionnaire contre
``api://<appId agent>/access_as_user``. Saut 2 : l'application de l'agent échange ce jeton contre
``api://<MCP_API_CLIENT_ID>/access_as_user`` ; le ``azp`` du jeton final est donc l'agent, ce que
le serveur MCP filtre. Fabriques injectables pour les tests (aucun réseau).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from azure.core.exceptions import AzureError
from azure.identity import (
    ManagedIdentityCredential,
    OnBehalfOfCredential,
    get_bearer_token_provider,
)

from ...domain.ports import AgentOuOrchestrateur, ErreurOutil
from .config import ConfigCluster
from .jetons import PORTEE_FEDERATION, credential_application

NON_CONFIGURE = "OBO_NON_CONFIGURE"


class JetonsAgents:
    def __init__(
        self,
        cfg: ConfigCluster,
        fabrique_obo: Callable[..., Any] = OnBehalfOfCredential,
        fabrique_credential: Callable[..., Any] = credential_application,
    ) -> None:
        self._cfg, self._obo, self._credential = cfg, fabrique_obo, fabrique_credential
        self._fournisseurs: dict[str, Callable[[], str]] = {}

    def _assertion(self) -> dict[str, Any]:
        secret = self._cfg.insurflow_client_secret
        if secret and secret.get_secret_value():
            return {"client_secret": secret.get_secret_value()}
        if self._cfg.azure_uami_client_id:
            identite = ManagedIdentityCredential(client_id=self._cfg.azure_uami_client_id)
            return {"client_assertion_func": lambda: identite.get_token(PORTEE_FEDERATION).token}
        raise ErreurOutil(NON_CONFIGURE, "ni INSURFLOW_CLIENT_SECRET ni AZURE_UAMI_CLIENT_ID")

    def _echanger(self, client_id: str, jeton: str, cible: str) -> str:
        credential = self._obo(
            self._cfg.azure_tenant_id, client_id, user_assertion=jeton, **self._assertion()
        )
        try:
            return str(credential.get_token(f"api://{cible}/access_as_user").token)
        except AzureError as exc:
            raise ErreurOutil("OBO_REFUSE", "Jeton On-Behalf-Of refusé") from exc

    def pour_mcp(self, agent: AgentOuOrchestrateur, jeton_gestionnaire: str) -> str:
        """Synchrone (SDK azure-identity) : appelé hors de la boucle d'événements."""
        cfg = self._cfg
        app_agent = cfg.client_agent(agent)
        if not (cfg.insurflow_cluster_client_id and app_agent and cfg.mcp_api_client_id):
            raise ErreurOutil(NON_CONFIGURE, f"application Entra manquante pour {agent}")
        intermediaire = self._echanger(
            cfg.insurflow_cluster_client_id, jeton_gestionnaire, app_agent
        )
        return self._echanger(app_agent, intermediaire, cfg.mcp_api_client_id)

    def fournisseur_llm(self, agent: AgentOuOrchestrateur) -> Callable[[], str]:
        """Fournisseur de jeton rafraîchi par azure-identity, mémorisé par agent."""
        if agent not in self._fournisseurs:
            cfg = self._cfg
            secret = cfg.insurflow_client_secret
            credential = self._credential(
                cfg.azure_tenant_id,
                cfg.client_agent(agent),
                secret.get_secret_value() if secret else None,
                cfg.azure_uami_client_id,
            )
            if credential is None or not cfg.llm_audience:
                raise ErreurOutil(NON_CONFIGURE, f"jeton LLM non configuré pour {agent}")
            self._fournisseurs[agent] = get_bearer_token_provider(
                credential, f"{cfg.llm_audience}/.default"
            )
        return self._fournisseurs[agent]

    def pour_llm(self, agent: AgentOuOrchestrateur) -> str:
        return self.fournisseur_llm(agent)()
