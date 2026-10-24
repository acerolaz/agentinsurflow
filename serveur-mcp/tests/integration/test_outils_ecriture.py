"""Intégration — outils d'écriture via le protocole MCP : matrice, schéma, corps, erreurs."""

from __future__ import annotations

from typing import Any

import pytest
from fakes_mcp import FauxCalculateur, FauxCorpus, FauxDossiers, FauxJetons
from jetons_mcp_de_test import AZP_ORCHESTRATEUR, AZP_REDACTEUR, config_auth, creer
from session_mcp import FauxJwks, session_mcp

from agentinsurflow_mcp.api.app import creer_app
from agentinsurflow_mcp.api.serveur import ServeurMcp
from agentinsurflow_mcp.domain.models import ErreurOutil

FICHE = {
    "decision": "ACCEPTE",
    "contrat_type": "tous_risques",
    "score": 12.5,
    "version_bareme": "2026.1",
    "regle_ids": ["R1"],
    "motifs": ["bon profil"],
    "citations": ["art. 3"],
}


def _app(dossiers: FauxDossiers) -> Any:
    application = creer_app(
        ServeurMcp(FauxJetons(), FauxCorpus(), dossiers, FauxCalculateur(), "test")
    )
    application.state.config_auth = config_auth()
    application.state.jwks = FauxJwks()
    return application


async def test_saga_enregistre_un_brouillon() -> None:
    dossiers = FauxDossiers()
    args = {
        "numero_contrat": "AIF/1",
        "fiche": FICHE,
        "prime": {"prime_ttc": 480, "periodicite": "mensuelle", "date_effet": "2026-11-01"},
    }
    async with session_mcp(_app(dossiers), creer(AZP_ORCHESTRATEUR)) as s:
        r = await s.call_tool("enregistrer_brouillon", args)
    assert (r.isError, r.structuredContent) == (False, {"ecrit": True})
    assert dossiers.ecritures[0][3]["prime"]["date_effet"] == "2026-11-01"
    assert dossiers.ecritures[0][3]["fiche"] == FICHE


async def test_saga_change_le_statut() -> None:
    dossiers = FauxDossiers()
    args = {"numero_contrat": "AIF/1", "statut": "REVUE_HUMAINE"}
    async with session_mcp(_app(dossiers), creer(AZP_ORCHESTRATEUR)) as s:
        r = await s.call_tool("update_statut_dossier", args)
    assert (r.isError, r.structuredContent) == (False, {"ecrit": True})
    assert dossiers.ecritures == [
        ("statut", "obo-underwriting", "AIF/1", {"statut": "REVUE_HUMAINE", "validation": None})
    ]


async def test_schema_du_brouillon_publie_les_champs_de_la_fiche() -> None:
    async with session_mcp(_app(FauxDossiers()), creer(AZP_ORCHESTRATEUR)) as s:
        outils = {o.name: o for o in (await s.list_tools()).tools}
    assert {"enregistrer_brouillon", "update_statut_dossier"} <= outils.keys()
    fiche = outils["enregistrer_brouillon"].inputSchema["$defs"]["Fiche"]["properties"]
    assert set(fiche) == set(FICHE)


@pytest.mark.parametrize(
    ("outil", "args"),
    [
        ("enregistrer_brouillon", {"numero_contrat": "A", "fiche": FICHE}),
        ("update_statut_dossier", {"numero_contrat": "A", "statut": "REFUSE"}),
    ],
)
async def test_redacteur_ne_peut_pas_ecrire(outil: str, args: dict[str, Any]) -> None:
    dossiers = FauxDossiers()
    async with session_mcp(_app(dossiers), creer(AZP_REDACTEUR)) as s:
        r = await s.call_tool(outil, args)
    assert (r.isError, r.structuredContent) == (True, {"code": "UNAUTHORIZED_TOOL"})
    assert dossiers.ecritures == []


@pytest.mark.parametrize("code", ["CONTRAT_INTROUVABLE", "ARGUMENTS_INVALIDES"])
async def test_update_statut_erreur_is_error_avec_code(code: str) -> None:
    app = _app(FauxDossiers(ErreurOutil(code, "x")))
    async with session_mcp(app, creer(AZP_ORCHESTRATEUR)) as s:
        r = await s.call_tool("update_statut_dossier", {"numero_contrat": "X", "statut": "ACCEPTE"})
    assert (r.isError, r.structuredContent) == (True, {"code": code})
