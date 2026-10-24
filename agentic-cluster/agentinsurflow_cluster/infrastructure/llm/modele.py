"""Modèle de chat du cluster : ``ChatOpenAI`` vers la gateway (``/api/llm/v1/``), sans clé.

Le jeton est celui de l'application de l'agent (rôle ``LLM``), rafraîchi par azure-identity.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from ...domain.models import NomAgent
from ...domain.ports import ErreurOutil
from ...domain.reglages import ReglageAgent
from ..entra.config import ConfigCluster
from ..entra.obo import JetonsAgents


def modele_chat(
    reglage: ReglageAgent, agent: NomAgent, cfg: ConfigCluster, jetons: JetonsAgents
) -> BaseChatModel | None:
    """``None`` (⇒ repli) si le LLM est désactivé ou non configuré."""
    if not (cfg.insurflow_llm_actif and cfg.llm_audience):
        return None
    try:
        fournisseur = jetons.fournisseur_llm(agent)
    except ErreurOutil:
        return None
    return ChatOpenAI(
        base_url=f"{cfg.gateway_url.rstrip('/')}/api/llm/v1/",
        api_key=fournisseur,
        model=reglage.modele,
        temperature=reglage.temperature,
        max_completion_tokens=reglage.max_tokens,
        timeout=cfg.insurflow_llm_delai_s,
        max_retries=0,
    )
