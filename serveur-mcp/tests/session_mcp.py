"""Aides des tests d'intégration MCP : faux JWKS et session cliente du SDK sur l'ASGI en mémoire."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from jetons_mcp_de_test import CLE_PUBLIQUE
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

URL = "http://test/mcp"


class FauxJwks:
    def get_signing_key_from_jwt(self, jeton: str) -> Any:
        return type("Cle", (), {"key": CLE_PUBLIQUE})()


def client_http(
    app: Any, jeton: str | None, supplementaires: dict[str, str] | None = None
) -> httpx.AsyncClient:
    entetes = {"Authorization": f"Bearer {jeton}"} if jeton else {}
    entetes.update(supplementaires or {})
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", headers=entetes
    )


@asynccontextmanager
async def session_mcp(
    app: Any, jeton: str, entetes: dict[str, str] | None = None
) -> AsyncIterator[ClientSession]:
    # le cycle de vie démarre le gestionnaire de sessions MCP (dans la même tâche que le test)
    async with app.router.lifespan_context(app), client_http(app, jeton, entetes) as http:
        async with streamable_http_client(URL, http_client=http) as (lire, ecrire, _):
            async with ClientSession(lire, ecrire) as session:
                await session.initialize()
                yield session
