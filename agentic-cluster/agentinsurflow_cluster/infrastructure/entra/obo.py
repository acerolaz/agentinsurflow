"""Jetons par agent : OBO en deux sauts vers le MCP, fournisseur de jeton d'application vers le LLM.

Saut 1 : l'application ``agentic-cluster`` échange le jeton du gestionnaire contre
``api://<appId agent>/access_as_user``. Saut 2 : l'application de l'agent échange ce jeton contre
``api://<MCP_API_CLIENT_ID>/access_as_user`` ; le ``azp`` du jeton final est donc l'agent, ce que
le serveur MCP filtre. Fabriques et horloge injectables pour les tests (aucun réseau).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from azure.core.exceptions import AzureError
from azure.identity import OnBehalfOfCredential, get_bearer_token_provider

from ...domain.models import NomAgent
from ...domain.ports import AgentOuOrchestrateur, ErreurOutil
from .config import ConfigCluster
from .jetons import credential_application, source_assertion

NON_CONFIGURE = "OBO_NON_CONFIGURE"
MARGE_S = 60  # un jeton mis en cache n'est rendu que s'il reste plus que cette marge


class JetonsAgents:
    def __init__(
        self,
        cfg: ConfigCluster,
        fabrique_obo: Callable[..., Any] = OnBehalfOfCredential,
        fabrique_credential: Callable[..., Any] = credential_application,
        horloge: Callable[[], float] = time.time,
    ) -> None:
        self._cfg, self._obo, self._credential, self._horloge = (
            cfg,
            fabrique_obo,
            fabrique_credential,
            horloge,
        )
        self._assertion = source_assertion(cfg)  # identité managée créée une seule fois
        self._fournisseurs: dict[str, Callable[[], str]] = {}
        # ponytail: cache en mémoire par (agent, jeton gestionnaire), purgé à l'écriture ;
        # pas de verrou (écrasement concurrent sans effet), cache partagé si plusieurs réplicas.
        self._cache: dict[tuple[str, str], tuple[str, float]] = {}

    def _echanger(self, client_id: str, jeton: str, cible: str) -> Any:
        if self._assertion is None:
            raise ErreurOutil(NON_CONFIGURE, "ni INSURFLOW_CLIENT_SECRET ni AZURE_UAMI_CLIENT_ID")
        credential = self._obo(
            self._cfg.azure_tenant_id, client_id, user_assertion=jeton, **self._assertion
        )
        try:
            return credential.get_token(f"api://{cible}/access_as_user")
        except AzureError as exc:
            raise ErreurOutil("OBO_REFUSE", "Jeton On-Behalf-Of refusé") from exc

    def pour_mcp(self, agent: AgentOuOrchestrateur, jeton_gestionnaire: str) -> str:
        """Synchrone (SDK azure-identity) : appelé hors de la boucle d'événements."""
        maintenant = self._horloge()
        cle = (agent, jeton_gestionnaire)
        if (en_cache := self._cache.get(cle)) and en_cache[1] - MARGE_S > maintenant:
            return en_cache[0]
        cfg = self._cfg
        app_agent = cfg.client_agent(agent)
        if not (cfg.insurflow_cluster_client_id and app_agent and cfg.mcp_api_client_id):
            raise ErreurOutil(NON_CONFIGURE, f"application Entra manquante pour {agent}")
        intermediaire = self._echanger(
            cfg.insurflow_cluster_client_id, jeton_gestionnaire, app_agent
        )
        final = self._echanger(app_agent, intermediaire.token, cfg.mcp_api_client_id)
        self._cache = {k: v for k, v in self._cache.items() if v[1] - MARGE_S > maintenant}
        self._cache[cle] = (str(final.token), float(final.expires_on))
        return str(final.token)

    def fournisseur_llm(self, agent: NomAgent) -> Callable[[], str]:
        """Fournisseur de jeton rafraîchi par azure-identity, mémorisé par agent."""
        if agent not in self._fournisseurs:
            cfg = self._cfg
            app_agent = cfg.client_agent(agent)
            if not (self._assertion and app_agent and cfg.llm_audience):
                raise ErreurOutil(NON_CONFIGURE, f"jeton LLM non configuré pour {agent}")
            credential = self._credential(cfg.azure_tenant_id, app_agent, self._assertion)
            self._fournisseurs[agent] = get_bearer_token_provider(
                credential, f"{cfg.llm_audience}/.default"
            )
        return self._fournisseurs[agent]
