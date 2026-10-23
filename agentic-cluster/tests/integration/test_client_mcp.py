"""TI — ``ClientMcpGateway`` face à un vrai serveur MCP (SDK, FastMCP) servi en mémoire.

Choix : un FastMCP minimal (un outil permis, un outil refusé qui répond comme le serveur-mcp :
``isError`` + ``structuredContent={"code": …}``). Le vrai ``ServeurMcp`` est un autre service : on
n'importe pas d'un service à l'autre ; son contrat de refus est couvert par ses propres tests.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent

from agentinsurflow_cluster.domain.ports import ErreurOutil
from agentinsurflow_cluster.infrastructure.mcp.client import ClientMcpGateway

recus: list[dict[str, str]] = []


def _serveur() -> FastMCP:
    mcp = FastMCP("faux", stateless_http=True, json_response=True)
    mcp.settings.transport_security = None

    @mcp.tool()
    def lister_pieces(numero_contrat: str) -> dict[str, Any]:
        return {"statut": "complet", "numero_contrat": numero_contrat}

    @mcp.tool()
    def update_statut_dossier() -> CallToolResult:
        return CallToolResult(
            content=[TextContent(type="text", text="refus")],
            structuredContent={"code": "UNAUTHORIZED_TOOL"},
            isError=True,
        )

    return mcp


@asynccontextmanager
async def _client() -> AsyncIterator[ClientMcpGateway]:
    # le cycle de vie MCP doit s'ouvrir et se fermer dans la tâche du test (pas dans une fixture)
    mcp = _serveur()
    app = mcp.streamable_http_app()

    async def trace(requete: httpx.Request) -> None:
        recus.append(dict(requete.headers))

    async with app.router.lifespan_context(app):
        http = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            event_hooks={"request": [trace]},
        )
        yield ClientMcpGateway("http://test", _FauxJetons(), fabrique_http=lambda e: _avec(http, e))
        await http.aclose()


class _FauxJetons:
    def pour_mcp(self, agent: str, jeton_gestionnaire: str) -> str:
        assert (agent, jeton_gestionnaire) == ("analyste", "jeton-gestionnaire")
        return "jeton-mcp"


def _avec(http: httpx.AsyncClient, entetes: dict[str, str]) -> httpx.AsyncClient:
    http.headers.update(entetes)
    return http


async def test_appel_autorise_rend_le_dict() -> None:
    async with _client() as client:
        resultat = await client.appeler(
            "analyste", "jeton-gestionnaire", "lister_pieces", {"numero_contrat": "A"}
        )
    assert resultat == {"statut": "complet", "numero_contrat": "A"}
    assert all(r.get("authorization") == "Bearer jeton-mcp" for r in recus)


async def test_refus_leve_erreur_outil_avec_le_code() -> None:
    async with _client() as client:
        with pytest.raises(ErreurOutil) as exc:
            await client.appeler("analyste", "jeton-gestionnaire", "update_statut_dossier", {})
    assert exc.value.code == "UNAUTHORIZED_TOOL"
