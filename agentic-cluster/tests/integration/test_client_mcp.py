"""TI — ``ClientMcpGateway`` face à un vrai serveur MCP (SDK, FastMCP) servi en mémoire.

Choix : un FastMCP minimal (un outil permis, un outil refusé qui répond comme le serveur-mcp :
``isError`` + ``structuredContent={"code": …}``). Le vrai ``ServeurMcp`` est un autre service : on
n'importe pas d'un service à l'autre ; son contrat de refus est couvert par ses propres tests.
"""

from __future__ import annotations

import asyncio
import time
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
TRACEPARENT = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"


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
        yield ClientMcpGateway(
            "http://test",
            _FauxJetons(),
            traceparent=lambda: TRACEPARENT,
            fabrique_http=lambda e: _avec(http, e),
        )
        await http.aclose()


class _FauxJetons:
    def pour_mcp(self, agent: str, jeton_gestionnaire: str) -> str:
        assert (agent, jeton_gestionnaire) == ("analyste", "jeton-gestionnaire")
        return "jeton-mcp"


def _avec(http: httpx.AsyncClient, entetes: dict[str, str]) -> httpx.AsyncClient:
    http.headers.update(entetes)
    return http


async def test_appel_autorise_rend_le_dict() -> None:
    recus.clear()
    async with _client() as client:
        resultat = await client.appeler(
            "analyste", "jeton-gestionnaire", "lister_pieces", {"numero_contrat": "A"}
        )
    assert resultat == {"statut": "complet", "numero_contrat": "A"}
    assert recus
    assert all(r.get("authorization") == "Bearer jeton-mcp" for r in recus)
    assert all(r.get("traceparent") == TRACEPARENT for r in recus)


async def test_refus_leve_erreur_outil_avec_le_code() -> None:
    async with _client() as client:
        with pytest.raises(ErreurOutil) as exc:
            await client.appeler("analyste", "jeton-gestionnaire", "update_statut_dossier", {})
    assert exc.value.code == "UNAUTHORIZED_TOOL"


async def test_panne_de_transport_devient_mcp_indisponible() -> None:
    def refuse(requete: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("injoignable", request=requete)

    client = ClientMcpGateway(
        "http://test",
        _FauxJetons(),
        fabrique_http=lambda e: httpx.AsyncClient(
            transport=httpx.MockTransport(refuse), base_url="http://test", headers=e
        ),
    )
    with pytest.raises(ErreurOutil) as exc:
        await client.appeler("analyste", "jeton-gestionnaire", "lister_pieces", {})
    assert exc.value.code == "MCP_INDISPONIBLE"


class _JetonsBloques:
    def pour_mcp(self, agent: str, jeton_gestionnaire: str) -> str:
        time.sleep(0.5)  # OBO Entra qui ne répond pas (000010 en staging, 27/10 : 26 s)
        return "jeton-mcp"


async def test_appel_trop_long_devient_mcp_indisponible() -> None:
    client = ClientMcpGateway("http://test", _JetonsBloques(), delai_s=0.05)
    with pytest.raises(ErreurOutil) as exc:
        await client.appeler("pieces", "jeton-gestionnaire", "lister_pieces", {})
    assert (exc.value.code, str(exc.value)) == ("MCP_INDISPONIBLE", "TimeoutError")


class _HttpAnnule:
    async def __aenter__(self) -> None:
        raise BaseExceptionGroup("x", [asyncio.CancelledError()])

    async def __aexit__(self, *exc: object) -> None:
        return None


async def test_annulation_seule_est_relancee_telle_quelle() -> None:
    client = ClientMcpGateway(
        "http://test",
        _FauxJetons(),
        fabrique_http=lambda e: _HttpAnnule(),  # type: ignore[arg-type,return-value]
    )
    with pytest.raises(BaseExceptionGroup) as exc:
        await client.appeler("analyste", "jeton-gestionnaire", "lister_pieces", {})
    assert not isinstance(exc.value, ErreurOutil)
    assert isinstance(exc.value.exceptions[0], asyncio.CancelledError)
