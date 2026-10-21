"""Unitaires — OBO : sans secret local ni identité managée, refus propre (aucun appel Entra)."""

from __future__ import annotations

import pytest
from fakes_mcp import appelant

from agentinsurflow_mcp.domain.models import ErreurOutil
from agentinsurflow_mcp.infrastructure.entra.obo import ConfigObo, JetonsEntra


def _config() -> ConfigObo:
    return ConfigObo(  # type: ignore[call-arg]
        _env_file=None,
        azure_tenant_id="t",
        mcp_api_client_id="m",
        rag_api_client_id="r",
        underwriting_api_client_id="u",
    )


@pytest.mark.parametrize("cfg", [None, _config()])
async def test_obo_impossible_dossiers_indisponibles(cfg: ConfigObo | None) -> None:
    with pytest.raises(ErreurOutil) as exc:
        await JetonsEntra(cfg).obo(appelant(), "rag")
    assert exc.value.code == "DOSSIERS_INDISPONIBLES"
