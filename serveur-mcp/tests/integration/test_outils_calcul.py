"""Intégration — outils ``evaluer_risque`` et ``calculer_prime`` via le protocole MCP."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fakes_mcp import VUE_SEED_1, FauxCalculateur, FauxCorpus, FauxDossiers, FauxJetons
from jetons_mcp_de_test import (
    AZP_ACTUAIRE,
    AZP_ANALYSTE,
    AZP_ORCHESTRATEUR,
    AZP_REDACTEUR,
    config_auth,
    creer,
)
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from session_mcp import FauxJwks, session_mcp

from agentinsurflow_mcp.api.app import creer_app
from agentinsurflow_mcp.api.serveur import ServeurMcp
from agentinsurflow_mcp.domain.models import ErreurOutil
from agentinsurflow_mcp.infrastructure.fonction_calcul.client import ClientCalcul, ConfigCalcul


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
    [
        (AZP_ORCHESTRATEUR, "calculer_prime"),
        (AZP_ORCHESTRATEUR, "evaluer_risque"),
        (AZP_ACTUAIRE, "evaluer_risque"),
        (AZP_REDACTEUR, "evaluer_risque"),
        (AZP_REDACTEUR, "calculer_prime"),
    ],
)
async def test_outil_non_autorise(azp: str, outil: str) -> None:
    calc = FauxCalculateur()
    async with session_mcp(_app(calc), creer(azp)) as s:
        r = await s.call_tool(outil, {"numero_contrat": "X"})
    assert (r.isError, r.structuredContent) == (True, {"code": "UNAUTHORIZED_TOOL"})
    assert calc.appels == []


async def test_actuaire_ne_voit_que_calculer_prime() -> None:
    async with session_mcp(_app(FauxCalculateur()), creer(AZP_ACTUAIRE)) as s:
        assert [t.name for t in (await s.list_tools()).tools] == ["calculer_prime"]


@pytest.mark.parametrize(
    ("azp", "outil"),
    [(AZP_ANALYSTE, "evaluer_risque"), (AZP_ACTUAIRE, "calculer_prime")],
)
@pytest.mark.parametrize("code", ["DONNEE_HORS_BAREME", "CALCUL_INDISPONIBLE"])
async def test_erreur_du_calcul_is_error_avec_code(azp: str, outil: str, code: str) -> None:
    app = _app(FauxCalculateur(ErreurOutil(code, "x")))
    async with session_mcp(app, creer(azp)) as s:
        r = await s.call_tool(outil, {"numero_contrat": "X"})
    assert (r.isError, r.structuredContent) == (True, {"code": code})


@pytest.mark.parametrize(
    ("azp", "outil"),
    [(AZP_ANALYSTE, "evaluer_risque"), (AZP_ACTUAIRE, "calculer_prime")],
)
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


async def test_span_du_client_sans_donnee_du_contrat(
    spans: InMemorySpanExporter, monkeypatch: pytest.MonkeyPatch
) -> None:
    corps = {
        "version_bareme": "bareme-2026.10-v1",
        "decision": "ACCEPTE",
        "prime_ttc_annuelle": "819.73",
    }
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=corps))
    )
    monkeypatch.setattr(
        "agentinsurflow_mcp.infrastructure.fonction_calcul.client.credential_application",
        lambda *a: type("C", (), {"get_token": lambda s, p: type("J", (), {"token": "j"})()})(),
    )
    calc = ClientCalcul(http, ConfigCalcul(calcul_url="http://calcul", calcul_audience="api://c"))
    await calc.evaluer({"crm": "0.9"})
    (span,) = [s for s in spans.get_finished_spans() if s.name == "calcul.appeler"]
    attributs = dict(span.attributes or {})
    assert attributs["calcul.route"] == "/evaluer"
    assert attributs["http.status_code"] == 200
    assert attributs["resultat.code"] == "OK"
    assert attributs["bareme.version"] == "bareme-2026.10-v1"
    valeurs = " ".join(str(v) for v in attributs.values())
    for interdit in ("0.9", "819.73", "ACCEPTE"):
        assert interdit not in valeurs
