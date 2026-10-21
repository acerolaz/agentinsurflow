"""Intégration — outils de lecture ``search_rag`` et ``get_contrat`` via le protocole MCP."""

from __future__ import annotations

from typing import Any

import pytest
from fakes_mcp import FauxCorpus, FauxDossiers, FauxJetons
from jetons_mcp_de_test import AZP_ORCHESTRATEUR, AZP_REDACTEUR, config_auth, creer
from session_mcp import FauxJwks, session_mcp

from agentinsurflow_mcp.api.app import creer_app
from agentinsurflow_mcp.api.serveur import ServeurMcp
from agentinsurflow_mcp.domain.models import ErreurOutil


def _app(corpus: FauxCorpus, dossiers: FauxDossiers) -> Any:
    application = creer_app(ServeurMcp(FauxJetons(), corpus, dossiers, "test"))
    application.state.config_auth = config_auth()
    application.state.jwks = FauxJwks()
    return application


async def test_orchestrateur_lit_un_contrat() -> None:
    app = _app(FauxCorpus(), FauxDossiers())
    async with session_mcp(app, creer(AZP_ORCHESTRATEUR)) as s:
        r = await s.call_tool("get_contrat", {"numero_contrat": "AIF/1"})
    assert r.isError is False
    assert r.structuredContent == {"numero_contrat": "AIF/1"}


async def test_redacteur_cherche_dans_le_corpus() -> None:
    corpus = FauxCorpus()
    async with session_mcp(_app(corpus, FauxDossiers()), creer(AZP_REDACTEUR)) as s:
        r = await s.call_tool("search_rag", {"question": "franchise ?", "top_k": 2})
    assert r.isError is False
    assert r.structuredContent == {"statut": "OK", "resultats": [{"texte": "extrait"}]}
    assert corpus.appels == [("obo-rag", "franchise ?", 2)]


async def test_description_de_search_rag_dit_ce_qu_il_ne_fait_pas() -> None:
    async with session_mcp(_app(FauxCorpus(), FauxDossiers()), creer(AZP_REDACTEUR)) as s:
        outil = (await s.list_tools()).tools[0]
    assert "Ne rédige aucune réponse" in (outil.description or "")
    assert "NOT_FOUND_IN_CORPUS" in (outil.description or "")


@pytest.mark.parametrize(
    "code", ["NOT_FOUND_IN_CORPUS", "DOSSIERS_INDISPONIBLES", "ARGUMENTS_INVALIDES"]
)
async def test_search_rag_erreur_is_error_avec_code(code: str) -> None:
    app = _app(FauxCorpus(ErreurOutil(code, "x")), FauxDossiers())
    async with session_mcp(app, creer(AZP_REDACTEUR)) as s:
        r = await s.call_tool("search_rag", {"question": "q"})
    assert (r.isError, r.structuredContent) == (True, {"code": code})


@pytest.mark.parametrize(
    "code", ["CONTRAT_INTROUVABLE", "DOSSIERS_INDISPONIBLES", "ARGUMENTS_INVALIDES"]
)
async def test_get_contrat_erreur_is_error_avec_code(code: str) -> None:
    app = _app(FauxCorpus(), FauxDossiers(ErreurOutil(code, "x")))
    async with session_mcp(app, creer(AZP_ORCHESTRATEUR)) as s:
        r = await s.call_tool("get_contrat", {"numero_contrat": "X"})
    assert (r.isError, r.structuredContent) == (True, {"code": code})
