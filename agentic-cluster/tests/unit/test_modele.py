"""TU — ``modele_chat`` : construction seule, aucun appel réseau."""

from __future__ import annotations

import inspect
from typing import Any

from fakes_cluster import REGLAGES

from agentinsurflow_cluster.infrastructure.entra.config import ConfigCluster
from agentinsurflow_cluster.infrastructure.entra.obo import JetonsAgents
from agentinsurflow_cluster.infrastructure.llm.modele import modele_chat


def _cfg(**surcharge: Any) -> ConfigCluster:
    base: dict[str, Any] = {
        "azure_tenant_id": "t",
        "insurflow_agent_analyste_client_id": "app-analyste",
        "insurflow_client_secret": "s",
        "llm_audience": "api://llm",
        "gateway_url": "http://gw:8000/",
    }
    return ConfigCluster(_env_file=None, **{**base, **surcharge})


def test_pointe_la_gateway_sans_reessai() -> None:
    cfg = _cfg()
    modele = modele_chat(REGLAGES["redacteur"], "analyste", cfg, JetonsAgents(cfg))
    assert modele is not None
    assert str(modele.openai_api_base) == "http://gw:8000/api/llm/v1/"  # type: ignore[attr-defined]
    assert modele.max_retries == 0  # type: ignore[attr-defined]


def test_modele_porte_le_reglage() -> None:
    cfg = _cfg(insurflow_agent_redacteur_client_id="app-redacteur")
    m = modele_chat(REGLAGES["redacteur"], "redacteur", cfg, JetonsAgents(cfg))
    assert m is not None
    assert (m.model_name, m.temperature, m.max_tokens) == ("gpt-4.1-mini", 0.2, 1200)  # type: ignore[attr-defined]


def test_desactive_ou_non_configure_rend_none() -> None:
    for surcharge in ({"insurflow_llm_actif": False}, {"llm_audience": ""}):
        cfg = _cfg(**surcharge)
        assert modele_chat(REGLAGES["redacteur"], "analyste", cfg, JetonsAgents(cfg)) is None


def test_le_client_asynchrone_recoit_un_fournisseur_awaitable() -> None:
    # langchain-openai enveloppe le callable synchrone (run_in_executor) : le jeton n'est pas
    # obtenu dans la boucle d'événements.
    cfg = _cfg()
    modele = modele_chat(REGLAGES["redacteur"], "analyste", cfg, JetonsAgents(cfg))
    assert modele is not None
    fournisseur = modele.root_async_client._api_key_provider  # type: ignore[attr-defined]
    assert inspect.iscoroutinefunction(fournisseur)
