"""Client MCP du cluster : toujours ``${GATEWAY_URL}/mcp``, jamais l'URL interne du serveur MCP.

ponytail: une session MCP (initialize + call_tool) par appel ; plafond = un aller-retour de plus par
outil, sans incidence au budget de 25 s pour <= 5 appels. Pool de sessions par agent si besoin.
``streamable_http_client`` remplace ``streamablehttp_client`` (déprécié dans mcp 1.30) : il
accepte un ``httpx.AsyncClient``, ce qui rend le transport injectable en test.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, Protocol

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import McpError

from ...domain.ports import AgentOuOrchestrateur, ErreurOutil


class _Jetons(Protocol):
    def pour_mcp(self, agent: AgentOuOrchestrateur, jeton_gestionnaire: str) -> str: ...


def _http_par_defaut(entetes: dict[str, str]) -> httpx.AsyncClient:
    return httpx.AsyncClient(headers=entetes, timeout=30)


class ClientMcpGateway:
    """Adapter de ``OutilsPort``."""

    def __init__(
        self,
        gateway_url: str,
        jetons: _Jetons,
        traceparent: Callable[[], str | None] = lambda: None,
        fabrique_http: Callable[[dict[str, str]], httpx.AsyncClient] = _http_par_defaut,
    ) -> None:
        self._url = f"{gateway_url.rstrip('/')}/mcp"
        self._jetons, self._traceparent, self._http = jetons, traceparent, fabrique_http

    async def appeler(
        self,
        agent: AgentOuOrchestrateur,
        jeton_gestionnaire: str,
        outil: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        jeton = await asyncio.to_thread(self._jetons.pour_mcp, agent, jeton_gestionnaire)
        entetes = {"Authorization": f"Bearer {jeton}"}
        if trace := self._traceparent():
            entetes["traceparent"] = trace
        try:
            async with self._http(entetes) as http:
                async with streamable_http_client(self._url, http_client=http) as (lire, ecrire, _):
                    async with ClientSession(lire, ecrire) as session:
                        await session.initialize()
                        resultat = await session.call_tool(outil, arguments)
        except (httpx.HTTPError, McpError) as e:  # panne de transport
            raise ErreurOutil("MCP_INDISPONIBLE", type(e).__name__) from e
        except BaseExceptionGroup as g:
            # une annulation seule doit remonter : sinon asyncio.timeout ne lève plus TimeoutError
            # (la condition de `subgroup` s'applique aussi aux groupes : on la restreint aux feuilles)
            autres = g.subgroup(
                lambda e: not isinstance(e, asyncio.CancelledError | BaseExceptionGroup)
            )
            if autres is None:
                raise
            raise ErreurOutil("MCP_INDISPONIBLE", type(g).__name__) from g
        if resultat.isError:
            code = (resultat.structuredContent or {}).get("code", "MCP_ERREUR")
            raise ErreurOutil(str(code))
        return dict(resultat.structuredContent or {})
