"""Unitaires — OBO : sans secret local ni identité managée, refus propre (aucun appel Entra) ;
refus d'Entra journalisé avec son message exact (#47)."""

from __future__ import annotations

from typing import Any

import pytest
from azure.core.exceptions import ClientAuthenticationError
from fakes_mcp import appelant
from pydantic import SecretStr

from agentinsurflow_mcp.domain.models import ErreurOutil
from agentinsurflow_mcp.infrastructure.entra import obo
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


class _CredentialRefuse:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def get_token(self, *portees: str) -> Any:
        raise ClientAuthenticationError("AADSTS65001: consentement manquant")


async def test_obo_refuse_message_entra_journalise(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(obo, "OnBehalfOfCredential", _CredentialRefuse)
    cfg = _config().model_copy(update={"mcp_client_secret": SecretStr("secret-local")})
    jeton = appelant().jeton
    with pytest.raises(ErreurOutil) as exc:
        await JetonsEntra(cfg).obo(appelant(), "underwriting")
    assert exc.value.code == "DOSSIERS_INDISPONIBLES"
    # #47 : le message Entra exact est journalisé, jamais le jeton du gestionnaire
    assert "AADSTS65001: consentement manquant" in caplog.text
    assert jeton not in caplog.text
