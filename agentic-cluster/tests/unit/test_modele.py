"""TU — ``modele_chat`` : construction seule, aucun appel réseau."""

from __future__ import annotations

import inspect
from typing import Any

from agentinsurflow_cluster.infrastructure.entra.config import ConfigCluster
from agentinsurflow_cluster.infrastructure.entra.obo import JetonsAgents
from agentinsurflow_cluster.infrastructure.llm.modele import modele_chat


def _cfg(**surcharge: Any) -> ConfigCluster:
    base: dict[str, Any] = {
        "azure_tenant_id": "t",
        "insurflow_agent_analyste_client_id": "app-analyste",
        "insurflow_client_secret": "s",
        "llm_audience": "api://llm",
        "azure_openai_deployment": "gpt",
        "gateway_url": "http://gw:8000/",
    }
    return ConfigCluster(_env_file=None, **{**base, **surcharge})


def test_pointe_la_gateway_sans_reessai() -> None:
    cfg = _cfg()
    modele = modele_chat("analyste", cfg, JetonsAgents(cfg))
    assert modele is not None
    assert str(modele.openai_api_base) == "http://gw:8000/api/llm/v1/"  # type: ignore[attr-defined]
    assert modele.max_retries == 0  # type: ignore[attr-defined]


def test_desactive_ou_non_configure_rend_none() -> None:
    for surcharge in ({"insurflow_llm_actif": False}, {"azure_openai_deployment": ""}):
        cfg = _cfg(**surcharge)
        assert modele_chat("analyste", cfg, JetonsAgents(cfg)) is None


def test_le_client_asynchrone_recoit_un_fournisseur_awaitable() -> None:
    # langchain-openai enveloppe le callable synchrone (run_in_executor) : le jeton n'est pas
    # obtenu dans la boucle d'événements.
    cfg = _cfg()
    modele = modele_chat("analyste", cfg, JetonsAgents(cfg))
    assert modele is not None
    fournisseur = modele.root_async_client._api_key_provider  # type: ignore[attr-defined]
    assert inspect.iscoroutinefunction(fournisseur)
