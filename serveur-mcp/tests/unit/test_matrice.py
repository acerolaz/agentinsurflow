"""Unitaires — matrice d'accès agent → outils (domaine pur)."""

from __future__ import annotations

import pytest

from agentinsurflow_mcp.domain.matrice import MATRICE, est_autorise, outils_autorises
from agentinsurflow_mcp.domain.models import Agent

ATTENDU: dict[Agent, set[str]] = {
    "orchestrateur": {
        "get_contrat",
        "enregistrer_brouillon",
        "update_statut_dossier",
        "enregistrer_etat",
    },
    "pieces": {"lister_pieces"},
    "analyste": {"evaluer_risque"},
    "redacteur": {"search_rag"},
    "actuaire": {"calculer_prime"},
}


@pytest.mark.parametrize("agent", ATTENDU)
def test_ligne_de_la_matrice(agent: Agent) -> None:
    assert outils_autorises(agent) == ATTENDU[agent]
    assert MATRICE[agent] == frozenset(ATTENDU[agent])


def test_agent_inconnu_n_a_aucun_outil() -> None:
    assert outils_autorises(None) == frozenset()
    assert est_autorise(None, "search_rag") is False


def test_redacteur_ne_peut_pas_ecrire() -> None:
    assert est_autorise("redacteur", "update_statut_dossier") is False
    assert est_autorise("redacteur", "search_rag") is True


def test_evaluer_risque_est_reserve_a_l_analyste() -> None:
    assert est_autorise("analyste", "evaluer_risque") is True
    assert est_autorise("orchestrateur", "evaluer_risque") is False


def test_separation_des_agents() -> None:
    assert est_autorise("actuaire", "update_statut_dossier") is False
    assert est_autorise("redacteur", "calculer_prime") is False
    assert outils_autorises("pieces") == {"lister_pieces"}
