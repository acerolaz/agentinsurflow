"""Unitaires — jeton d'application : secret local d'abord, puis identité managée fédérée."""

from __future__ import annotations

from typing import Any

import pytest
from azure.identity import ClientAssertionCredential, ClientSecretCredential

from agentinsurflow_mcp.infrastructure.entra import application as module
from agentinsurflow_mcp.infrastructure.entra.application import credential_application


def test_secret_local_prioritaire() -> None:
    c = credential_application("tenant", "client", "s3cret", "uami")
    assert isinstance(c, ClientSecretCredential)


def test_identite_managee_sans_secret() -> None:
    c = credential_application("tenant", "client", None, "uami")
    assert isinstance(c, ClientAssertionCredential)


def test_secret_vide_retombe_sur_identite() -> None:
    assert isinstance(credential_application("t", "c", "", "u"), ClientAssertionCredential)


@pytest.mark.parametrize(
    "args", [(None, "c", "s", "u"), ("t", None, "s", "u"), ("t", "c", None, None)]
)
def test_configuration_incomplete_renvoie_none(args: Any) -> None:
    assert credential_application(*args) is None


def test_exporte_la_portee_de_federation() -> None:
    assert module.PORTEE_FEDERATION == "api://AzureADTokenExchange/.default"
