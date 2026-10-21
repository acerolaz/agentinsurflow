"""Unitaires — matrice d'accès agent → outils (domaine pur)."""

from __future__ import annotations

import pytest

from agentinsurflow_mcp.domain.matrice import MATRICE, est_autorise, outils_autorises
from agentinsurflow_mcp.domain.models import Agent

ATTENDU: dict[Agent, set[str]] = {
    "orchestrateur": {
        "get_contrat",
        "evaluer_risque",
        "enregistrer_brouillon",
        "update_statut_dossier",
    },
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
