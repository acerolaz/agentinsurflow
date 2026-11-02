"""Intégration — outils ``evaluer_risque`` et ``calculer_prime`` via le protocole MCP."""

from __future__ import annotations

from typing import Any

import pytest
from fakes_mcp import VUE_SEED_1, FauxCalculateur, FauxCorpus, FauxDossiers, FauxJetons
from jetons_mcp_de_test import (
    AZP_ACTUAIRE,
    AZP_ANALYSTE,
    AZP_REDACTEUR,
    config_auth,
    creer,
)
from session_mcp import FauxJwks, session_mcp

from agentinsurflow_mcp.api.app import creer_app
from agentinsurflow_mcp.api.serveur import ServeurMcp
from agentinsurflow_mcp.domain.models import ErreurOutil


def _app(calc: FauxCalculateur, dossiers: FauxDossiers | None = None) -> Any:
    dossiers = dossiers or FauxDossiers(vue=VUE_SEED_1)
    application = creer_app(ServeurMcp(FauxJetons(), FauxCorpus(), dossiers, calc, "test"))
    application.state.config_auth = config_auth()
    application.state.jwks = FauxJwks()
    return application


async def test_analyste_evalue_le_risque() -> None:
    calc = FauxCalculateur()
    async with session_mcp(_app(calc), creer(AZP_ANALYSTE)) as s:
        r = await s.call_tool("evaluer_risque", {"numero_contrat": "AIF-2026-000001"})
    assert r.isError is False
    assert r.structuredContent == {"classe": "A", "decision": "ACCEPTE", "score": 0, "regles": []}


async def test_actuaire_calcule_la_prime() -> None:
    calc = FauxCalculateur()
    async with session_mcp(_app(calc), creer(AZP_ACTUAIRE)) as s:
        r = await s.call_tool("calculer_prime", {"numero_contrat": "AIF-2026-000001"})
    assert r.isError is False
    assert r.structuredContent == {"prime_ttc_annuelle": "819.73", "prime_mensuelle": "68.31"}


@pytest.mark.parametrize(
    ("azp", "outil"),
    [(AZP_REDACTEUR, "calculer_prime")],
)
async def test_outil_non_autorise(azp: str, outil: str) -> None:
    calc = FauxCalculateur()
    async with session_mcp(_app(calc), creer(azp)) as s:
        r = await s.call_tool(outil, {"numero_contrat": "X"})
    assert (r.isError, r.structuredContent) == (True, {"code": "UNAUTHORIZED_TOOL"})
    assert calc.appels == []


@pytest.mark.parametrize(
    ("azp", "outil", "code"), [(AZP_ANALYSTE, "evaluer_risque", "DONNEE_HORS_BAREME")]
)
async def test_erreur_du_calcul_is_error_avec_code(azp: str, outil: str, code: str) -> None:
    app = _app(FauxCalculateur(ErreurOutil(code, "x")))
    async with session_mcp(app, creer(azp)) as s:
        r = await s.call_tool(outil, {"numero_contrat": "X"})
    assert (r.isError, r.structuredContent) == (True, {"code": code})


@pytest.mark.parametrize(("azp", "outil"), [(AZP_ACTUAIRE, "calculer_prime")])
async def test_contrat_introuvable_is_error_avec_code(azp: str, outil: str) -> None:
    app = _app(FauxCalculateur(), FauxDossiers(ErreurOutil("CONTRAT_INTROUVABLE", "x")))
    async with session_mcp(app, creer(azp)) as s:
        r = await s.call_tool(outil, {"numero_contrat": "X"})
    assert (r.isError, r.structuredContent) == (True, {"code": "CONTRAT_INTROUVABLE"})


async def test_docstrings_citent_les_erreurs() -> None:
    async with session_mcp(_app(FauxCalculateur()), creer(AZP_ANALYSTE)) as s:
        evaluer = next(t for t in (await s.list_tools()).tools if t.name == "evaluer_risque")
    async with session_mcp(_app(FauxCalculateur()), creer(AZP_ACTUAIRE)) as s:
        prime = (await s.list_tools()).tools[0]
    for outil in (evaluer, prime):
        assert "DONNEE_HORS_BAREME" in (outil.description or "")
        assert "CALCUL_INDISPONIBLE" in (outil.description or "")
