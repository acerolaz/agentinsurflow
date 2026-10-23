"""TU — OBO en deux sauts : aucun réseau, ``OnBehalfOfCredential`` remplacé par un faux."""

from __future__ import annotations

from typing import Any

import pytest
from azure.core.exceptions import AzureError

from agentinsurflow_cluster.domain.ports import ErreurOutil
from agentinsurflow_cluster.infrastructure.entra.config import ConfigCluster
from agentinsurflow_cluster.infrastructure.entra.obo import JetonsAgents


class FauxObo:
    """Enregistre chaque échange ; le jeton rendu nomme sa cible."""

    journal: list[dict[str, Any]] = []
    refus_au_client: str | None = None

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
        if FauxObo.refus_au_client == self.client_id:
            raise AzureError("refusé")
        return type("Jeton", (), {"token": f"jeton[{portee}]", "expires_on": 1000.0})()


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
    FauxObo.refus_au_client = None


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


def test_ni_secret_ni_identite_refuse(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(
        "AZURE_UAMI_CLIENT_ID", raising=False
    )  # hermétique : `.env` exporté par make
    cfg = _cfg(insurflow_client_secret=None)
    with pytest.raises(ErreurOutil) as exc:
        JetonsAgents(cfg, fabrique_obo=FauxObo).pour_mcp("analyste", "j")
    assert exc.value.code == "OBO_NON_CONFIGURE"


def test_agent_sans_application_refuse() -> None:
    with pytest.raises(ErreurOutil) as exc:
        JetonsAgents(_cfg(), fabrique_obo=FauxObo).pour_mcp("pieces", "j")
    assert exc.value.code == "OBO_NON_CONFIGURE"
    assert FauxObo.journal == []


def test_deuxieme_appel_identique_sans_nouvel_echange() -> None:
    jetons = JetonsAgents(_cfg(), fabrique_obo=FauxObo, horloge=lambda: 0.0)
    premier = jetons.pour_mcp("analyste", "j")
    assert jetons.pour_mcp("analyste", "j") == premier
    assert len(FauxObo.journal) == 2


def test_jeton_proche_de_l_expiration_est_rechange() -> None:
    maintenant = [0.0]
    jetons = JetonsAgents(_cfg(), fabrique_obo=FauxObo, horloge=lambda: maintenant[0])
    jetons.pour_mcp("analyste", "j")
    maintenant[0] = 941.0  # 1000 - 60 s de marge = 940 : expiré
    jetons.pour_mcp("analyste", "j")
    assert len(FauxObo.journal) == 4


def test_autre_jeton_gestionnaire_est_rechange() -> None:
    jetons = JetonsAgents(_cfg(), fabrique_obo=FauxObo, horloge=lambda: 0.0)
    jetons.pour_mcp("analyste", "j1")
    jetons.pour_mcp("analyste", "j2")
    assert len(FauxObo.journal) == 4


def test_refus_entra_au_second_saut() -> None:
    FauxObo.refus_au_client = "app-analyste"
    with pytest.raises(ErreurOutil) as exc:
        JetonsAgents(_cfg(), fabrique_obo=FauxObo).pour_mcp("analyste", "j")
    assert exc.value.code == "OBO_REFUSE"
