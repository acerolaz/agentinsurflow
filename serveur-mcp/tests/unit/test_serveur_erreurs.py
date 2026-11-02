"""Unitaires — erreur d'outil rendue en isError avec son code, ports simulés."""

from __future__ import annotations

from typing import Any

import pytest
from fakes_mcp import VUE_SEED_1, FauxCalculateur, FauxCorpus, FauxDossiers, FauxJetons, appelant

from agentinsurflow_mcp.api.securite import appelant_courant
from agentinsurflow_mcp.api.serveur import ServeurMcp
from agentinsurflow_mcp.domain.models import Agent, ErreurOutil

STATUT = {"numero_contrat": "X", "statut": "REFUSE"}
CAS = [
    ("redacteur", "search_rag", {"question": "q"}, "NOT_FOUND_IN_CORPUS"),
    ("redacteur", "search_rag", {"question": "q"}, "DOSSIERS_INDISPONIBLES"),
    ("saga", "get_contrat", {"numero_contrat": "X"}, "CONTRAT_INTROUVABLE"),
    ("saga", "update_statut_dossier", STATUT, "ARGUMENTS_INVALIDES"),
    ("analyste", "evaluer_risque", {"numero_contrat": "X"}, "DONNEE_HORS_BAREME"),
    ("actuaire", "calculer_prime", {"numero_contrat": "X"}, "CALCUL_INDISPONIBLE"),
]  # fmt: skip


@pytest.mark.parametrize(("agent", "outil", "args", "code"), CAS)
async def test_erreur_d_outil_devient_is_error_avec_son_code(
    agent: Agent, outil: str, args: dict[str, Any], code: str
) -> None:
    erreur = ErreurOutil(code, "x")
    serveur = ServeurMcp(
        FauxJetons(), FauxCorpus(erreur), FauxDossiers(erreur, VUE_SEED_1), FauxCalculateur(erreur)
    )
    marque = appelant_courant.set(appelant(agent))
    try:
        r = await serveur.call_tool(outil, args)
    finally:
        appelant_courant.reset(marque)
    assert (r.isError, r.structuredContent) == (True, {"code": code})  # type: ignore[union-attr]
