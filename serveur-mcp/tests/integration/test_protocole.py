"""Intégration — protocole MCP (client du SDK) sur l'application en mémoire, jeton Entra exigé."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

import pytest
from fakes_mcp import FauxCalculateur, FauxCorpus, FauxDossiers, FauxJetons
from jetons_mcp_de_test import AZP_ORCHESTRATEUR, AZP_REDACTEUR, config_auth, creer
from jwt import PyJWKClientConnectionError
from mcp import ClientSession
from session_mcp import FauxJwks, client_http, session_mcp

from agentinsurflow_mcp.api.app import creer_app
from agentinsurflow_mcp.api.serveur import ServeurMcp
from agentinsurflow_mcp.domain.models import ErreurOutil


@pytest.fixture
def dossiers() -> FauxDossiers:
    return FauxDossiers(ErreurOutil("CONTRAT_INTROUVABLE", "Contrat introuvable"))


@pytest.fixture
def app(dossiers: FauxDossiers) -> Any:
    serveur = ServeurMcp(FauxJetons(), FauxCorpus(), dossiers, FauxCalculateur(), "test")
    application = creer_app(serveur)
    application.state.config_auth = config_auth()
    application.state.jwks = FauxJwks()
    return application


_client = client_http


Ouvrir = Callable[[str], AbstractAsyncContextManager[ClientSession]]


@pytest.fixture
def ouvrir(app: Any) -> Ouvrir:
    return lambda jeton: session_mcp(app, jeton)


async def test_sans_jeton_401(app: Any) -> None:
    async with _client(app, None) as c:
        r = await c.post("/mcp", json={})
    assert r.status_code == 401
    assert r.json()["code"] == "JETON_ABSENT"


async def test_jeton_invalide_401(app: Any) -> None:
    async with _client(app, "pas-un-jwt") as c:
        r = await c.post("/mcp", json={})
    assert (r.status_code, r.json()["code"]) == (401, "JETON_INVALIDE")


async def test_role_manquant_403(app: Any) -> None:
    async with _client(app, creer(roles=[])) as c:
        r = await c.post("/mcp", json={})
    assert (r.status_code, r.json()["code"]) == (403, "ROLE_MANQUANT")


class JwksInjoignable:
    def get_signing_key_from_jwt(self, jeton: str) -> Any:
        raise PyJWKClientConnectionError("Entra injoignable")


async def test_sans_configuration_entra_503(app: Any) -> None:
    app.state.config_auth = None
    async with _client(app, creer()) as c:
        r = await c.post("/mcp", json={})
    assert (r.status_code, r.json()["code"]) == (503, "AUTH_INDISPONIBLE")


async def test_jwks_injoignable_503_pas_401(app: Any) -> None:
    app.state.jwks = JwksInjoignable()
    async with _client(app, creer()) as c:
        r = await c.post("/mcp", json={})
    assert (r.status_code, r.json()["code"]) == (503, "AUTH_INDISPONIBLE")


async def test_health_sans_jeton(app: Any) -> None:
    async with _client(app, None) as c:
        assert (await c.get("/health")).status_code == 200


async def test_redacteur_ne_voit_que_search_rag(ouvrir: Ouvrir) -> None:
    async with ouvrir(creer(AZP_REDACTEUR)) as s:
        assert [t.name for t in (await s.list_tools()).tools] == ["search_rag"]


async def test_orchestrateur_voit_ses_outils(ouvrir: Ouvrir) -> None:
    async with ouvrir(creer(AZP_ORCHESTRATEUR)) as s:
        assert {t.name for t in (await s.list_tools()).tools} == {
            "update_statut_dossier",
            "enregistrer_brouillon",
            "get_contrat",
            "evaluer_risque",
        }


async def test_azp_inconnu_liste_vide(ouvrir: Ouvrir) -> None:
    async with ouvrir(creer("inconnu")) as s:
        assert (await s.list_tools()).tools == []


async def test_outil_autorise_appele(ouvrir: Ouvrir) -> None:
    async with ouvrir(creer(AZP_REDACTEUR)) as s:
        r = await s.call_tool("search_rag", {"question": "q"})
    assert r.isError is False


async def test_redacteur_appelle_update_statut_dossier_UNAUTHORIZED_TOOL_sans_appel_backend(
    ouvrir: Ouvrir, dossiers: FauxDossiers
) -> None:
    async with ouvrir(creer(AZP_REDACTEUR)) as s:
        r = await s.call_tool("update_statut_dossier", {})
    assert dossiers.ecritures == []
    assert r.isError is True
    assert r.structuredContent == {"code": "UNAUTHORIZED_TOOL"}


async def test_erreur_outil_en_resultat_is_error(ouvrir: Ouvrir) -> None:
    async with ouvrir(creer(AZP_ORCHESTRATEUR)) as s:
        r = await s.call_tool("get_contrat", {"numero_contrat": "X"})
    assert r.isError is True
    assert r.structuredContent == {"code": "CONTRAT_INTROUVABLE"}
