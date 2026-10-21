"""Intégration — protocole MCP (client du SDK) sur l'application en mémoire, jeton Entra exigé."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

import httpx
import pytest
from jetons_mcp_de_test import (
    AZP_ORCHESTRATEUR,
    AZP_REDACTEUR,
    CLE_PUBLIQUE,
    config_auth,
    creer,
)
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from agentinsurflow_mcp.api.app import creer_app
from agentinsurflow_mcp.api.serveur import ServeurMcp
from agentinsurflow_mcp.domain.models import ErreurOutil

URL = "http://test/mcp"


class FauxJwks:
    def get_signing_key_from_jwt(self, jeton: str) -> Any:
        return type("Cle", (), {"key": CLE_PUBLIQUE})()


class BackendQuiEchoue:
    """Port simulé : toute écriture vers le backend est un échec du test."""

    def ecrire(self) -> None:
        raise AssertionError("le backend ne doit pas être appelé")


@pytest.fixture
def backend() -> BackendQuiEchoue:
    return BackendQuiEchoue()


@pytest.fixture
def app(backend: BackendQuiEchoue) -> Any:
    serveur = ServeurMcp("test")

    @serveur.tool()
    def search_rag(question: str) -> str:
        return f"extraits pour {question}"

    @serveur.tool()
    def update_statut_dossier() -> str:
        backend.ecrire()
        return "ok"

    @serveur.tool()
    def get_contrat() -> str:
        raise ErreurOutil("CONTRAT_INTROUVABLE", "Contrat introuvable")

    application = creer_app(serveur)
    application.state.config_auth = config_auth()
    application.state.jwks = FauxJwks()
    return application


def _client(app: Any, jeton: str | None) -> httpx.AsyncClient:
    entetes = {"Authorization": f"Bearer {jeton}"} if jeton else {}
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", headers=entetes
    )


@asynccontextmanager
async def _session(app: Any, jeton: str) -> AsyncIterator[ClientSession]:
    # le cycle de vie démarre le gestionnaire de sessions MCP (dans la même tâche que le test)
    async with app.router.lifespan_context(app), _client(app, jeton) as http:
        async with streamable_http_client(URL, http_client=http) as (lire, ecrire, _):
            async with ClientSession(lire, ecrire) as session:
                await session.initialize()
                yield session


Ouvrir = Callable[[str], AbstractAsyncContextManager[ClientSession]]


@pytest.fixture
def ouvrir(app: Any) -> Ouvrir:
    return lambda jeton: _session(app, jeton)


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
            "get_contrat",
        }


async def test_azp_inconnu_liste_vide(ouvrir: Ouvrir) -> None:
    async with ouvrir(creer("inconnu")) as s:
        assert (await s.list_tools()).tools == []


async def test_outil_autorise_appele(ouvrir: Ouvrir) -> None:
    async with ouvrir(creer(AZP_REDACTEUR)) as s:
        r = await s.call_tool("search_rag", {"question": "q"})
    assert r.isError is False


async def test_redacteur_appelle_update_statut_dossier_UNAUTHORIZED_TOOL_sans_appel_backend(
    ouvrir: Ouvrir,
) -> None:
    async with ouvrir(creer(AZP_REDACTEUR)) as s:
        r = await s.call_tool("update_statut_dossier", {})
    assert r.isError is True
    assert r.structuredContent == {"code": "UNAUTHORIZED_TOOL"}


async def test_erreur_outil_en_resultat_is_error(ouvrir: Ouvrir) -> None:
    async with ouvrir(creer(AZP_ORCHESTRATEUR)) as s:
        r = await s.call_tool("get_contrat", {})
    assert r.isError is True
    assert r.structuredContent == {"code": "CONTRAT_INTROUVABLE"}
