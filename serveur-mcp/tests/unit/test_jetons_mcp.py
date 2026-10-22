"""Unitaires — validation du jeton Entra du serveur MCP et identification de l'agent par azp."""

from __future__ import annotations

import pytest
from jetons_mcp_de_test import (
    AZP_ACTUAIRE,
    AZP_ORCHESTRATEUR,
    AZP_REDACTEUR,
    CLE_ETRANGERE,
    CLE_PUBLIQUE,
    CLIENT_RAG,
    EMETTEUR_V1,
    config_auth,
    creer,
)

from agentinsurflow_mcp.infrastructure.entra.jetons import ErreurAuth, verifier_jeton

CFG = config_auth()


@pytest.mark.parametrize(
    ("azp", "agent"),
    [
        (AZP_ORCHESTRATEUR, "orchestrateur"),
        (AZP_REDACTEUR, "redacteur"),
        (AZP_ACTUAIRE, "actuaire"),
    ],
)
def test_agent_deduit_de_azp(azp: str, agent: str) -> None:
    appelant = verifier_jeton(creer(azp), CLE_PUBLIQUE, CFG)
    assert appelant.agent == agent
    assert appelant.azp == azp
    assert appelant.roles == {"Gestionnaire"}


def test_azp_inconnu_sans_agent() -> None:
    assert verifier_jeton(creer("inconnu"), CLE_PUBLIQUE, CFG).agent is None


def test_jeton_v1_lit_appid() -> None:
    jeton = creer(AZP_ACTUAIRE, azp_v1=True, iss=EMETTEUR_V1)
    appelant = verifier_jeton(jeton, CLE_PUBLIQUE, CFG)
    assert appelant.agent == "actuaire"
    assert appelant.jeton == jeton


def test_jeton_sans_azp_sans_agent() -> None:
    assert verifier_jeton(creer(None), CLE_PUBLIQUE, CFG).agent is None


def test_audience_de_rag_refusee() -> None:
    with pytest.raises(ErreurAuth):
        verifier_jeton(creer(aud=CLIENT_RAG), CLE_PUBLIQUE, CFG)


def test_jeton_absent_de_la_representation() -> None:
    jeton = creer()
    assert jeton not in repr(verifier_jeton(jeton, CLE_PUBLIQUE, CFG))


@pytest.mark.parametrize(
    "defaut",
    [
        {"expire_dans": -10},
        {"iss": "https://sts.windows.net/autre/"},
        {"cle": CLE_ETRANGERE},
        {"oid": ""},
    ],
    ids=["expire", "emetteur_etranger", "autre_cle", "sans_oid"],
)
def test_jeton_refuse(defaut: dict[str, object]) -> None:
    with pytest.raises(ErreurAuth):
        verifier_jeton(creer(**defaut), CLE_PUBLIQUE, CFG)  # type: ignore[arg-type]
