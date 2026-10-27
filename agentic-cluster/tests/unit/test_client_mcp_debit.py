"""TU — ``ClientMcpGateway`` face aux refus de la gateway (#122), ``httpx.MockTransport``."""

from __future__ import annotations

import httpx
import pytest

from agentinsurflow_cluster.domain.ports import ErreurOutil
from agentinsurflow_cluster.infrastructure.mcp.client import ClientMcpGateway


class _FauxJetons:
    def pour_mcp(self, agent: str, jeton_gestionnaire: str) -> str:
        return "jeton-mcp"


def _client(reponse: httpx.Response) -> ClientMcpGateway:
    transport = httpx.MockTransport(lambda _: reponse)
    return ClientMcpGateway(
        "http://gateway",
        _FauxJetons(),
        fabrique_http=lambda e: httpx.AsyncClient(transport=transport, headers=e),
    )


async def test_429_de_la_gateway_devient_trop_de_requetes() -> None:
    client = _client(httpx.Response(429, headers={"Retry-After": "17"}))

    with pytest.raises(ErreurOutil) as e:
        await client.appeler("analyste", "jeton", "get_contrat", {"numero_contrat": "AIF-1"})

    assert e.value.code == "TROP_DE_REQUETES"
    assert str(e.value) == "17"


async def test_429_sans_retry_after_attend_60_s() -> None:
    client = _client(httpx.Response(429))

    with pytest.raises(ErreurOutil) as e:
        await client.appeler("analyste", "jeton", "get_contrat", {"numero_contrat": "AIF-1"})

    assert (e.value.code, str(e.value)) == ("TROP_DE_REQUETES", "60")


async def test_500_reste_mcp_indisponible() -> None:
    client = _client(httpx.Response(500))

    with pytest.raises(ErreurOutil) as e:
        await client.appeler("analyste", "jeton", "get_contrat", {"numero_contrat": "AIF-1"})

    assert e.value.code == "MCP_INDISPONIBLE"
