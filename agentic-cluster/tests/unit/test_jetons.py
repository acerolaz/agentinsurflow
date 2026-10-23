"""TU — OBO en deux sauts : aucun réseau, ``OnBehalfOfCredential`` remplacé par un faux."""

from __future__ import annotations

from typing import Any

import pytest

from agentinsurflow_cluster.domain.ports import ErreurOutil
from agentinsurflow_cluster.infrastructure.entra.config import ConfigCluster
from agentinsurflow_cluster.infrastructure.entra.obo import JetonsAgents


class FauxObo:
    """Enregistre chaque échange ; le jeton rendu nomme sa cible."""

    journal: list[dict[str, Any]] = []

    def __init__(self, tenant: str, client_id: str, *, user_assertion: str, **assertion: Any):
        self.client_id, self.entree, self.assertion = client_id, user_assertion, assertion

    def get_token(self, portee: str) -> Any:
        FauxObo.journal.append(
            {
                "client": self.client_id,
                "entree": self.entree,
                "portee": portee,
                "assertion": sorted(self.assertion),
            }
        )
        return type("Jeton", (), {"token": f"jeton[{portee}]"})()


def _cfg(**surcharge: Any) -> ConfigCluster:
    base: dict[str, Any] = {
        "azure_tenant_id": "tenant",
        "insurflow_cluster_client_id": "app-cluster",
        "insurflow_agent_analyste_client_id": "app-analyste",
        "mcp_api_client_id": "app-mcp",
        "insurflow_client_secret": "secret-local",
    }
    return ConfigCluster(_env_file=None, **{**base, **surcharge})


@pytest.fixture(autouse=True)
def _vide() -> None:
    FauxObo.journal = []


def test_pour_mcp_fait_deux_echanges_dans_l_ordre() -> None:
    jetons = JetonsAgents(_cfg(), fabrique_obo=FauxObo)

    jeton = jetons.pour_mcp("analyste", "jeton-gestionnaire")

    assert FauxObo.journal == [
        {
            "client": "app-cluster",
            "entree": "jeton-gestionnaire",
            "portee": "api://app-analyste/access_as_user",
            "assertion": ["client_secret"],
        },
        {
            "client": "app-analyste",
            "entree": "jeton[api://app-analyste/access_as_user]",
            "portee": "api://app-mcp/access_as_user",
            "assertion": ["client_secret"],
        },
    ]
    assert jeton == "jeton[api://app-mcp/access_as_user]"


def test_sans_secret_l_assertion_est_federee() -> None:
    cfg = _cfg(insurflow_client_secret=None, azure_uami_client_id="uami")
    JetonsAgents(cfg, fabrique_obo=FauxObo).pour_mcp("analyste", "j")
    assert [e["assertion"] for e in FauxObo.journal] == [["client_assertion_func"]] * 2


def test_ni_secret_ni_identite_refuse() -> None:
    cfg = _cfg(insurflow_client_secret=None)
    with pytest.raises(ErreurOutil) as exc:
        JetonsAgents(cfg, fabrique_obo=FauxObo).pour_mcp("analyste", "j")
    assert exc.value.code == "OBO_NON_CONFIGURE"


def test_agent_sans_application_refuse() -> None:
    with pytest.raises(ErreurOutil) as exc:
        JetonsAgents(_cfg(), fabrique_obo=FauxObo).pour_mcp("pieces", "j")
    assert exc.value.code == "OBO_NON_CONFIGURE"
    assert FauxObo.journal == []


def test_pour_llm_est_un_jeton_d_application_de_l_agent() -> None:
    appels: list[tuple[str, str]] = []

    def fabrique(tenant: str, client_id: str, secret: str | None, uami: str | None) -> Any:
        class Cred:
            def get_token(self, *portees: str, **_: Any) -> Any:
                appels.append((client_id, portees[0]))
                return type("T", (), {"token": "jeton-llm", "expires_on": 4_000_000_000})()

        return Cred()

    cfg = _cfg(llm_audience="api://llm")
    assert JetonsAgents(cfg, fabrique_credential=fabrique).pour_llm("analyste") == "jeton-llm"
    assert appels == [("app-analyste", "api://llm/.default")]
