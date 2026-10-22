"""Unitaires — l'exportateur OTLP pose le jeton d'application, sans jamais le journaliser."""

from __future__ import annotations

import logging
from typing import Any

import pytest
import requests
from azure.core.exceptions import ClientAuthenticationError

from agentinsurflow_mcp.infrastructure.otel import telemetrie

JETON = "jeton-secret-xyz"


class _Credential:
    def __init__(self, echec: bool = False) -> None:
        self.portees: list[str] = []
        self._echec = echec

    def get_token(self, portee: str) -> Any:
        self.portees.append(portee)
        if self._echec:
            raise ClientAuthenticationError("refusé")
        return type("J", (), {"token": JETON})()


def _preparer(session: requests.Session) -> requests.PreparedRequest:
    requete = requests.Request("POST", "http://gateway:8000/v1/traces").prepare()
    return session.auth(requete)  # type: ignore[misc]


def test_session_pose_le_bearer_avec_la_bonne_portee() -> None:
    cred = _Credential()
    requete = _preparer(telemetrie.session_authentifiee(cred, "api://underwriting"))
    assert requete.headers["Authorization"] == f"Bearer {JETON}"
    assert cred.portees == ["api://underwriting/.default"]


def test_echec_azure_sans_en_tete_et_sans_jeton_dans_le_journal(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG):
        requete = _preparer(telemetrie.session_authentifiee(_Credential(echec=True), "api://u"))
    assert "Authorization" not in requete.headers
    assert "ClientAuthenticationError" in caplog.text
    assert JETON not in caplog.text


def _capturer(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    vus: dict[str, Any] = {}

    def faux(**kw: Any) -> str:
        vus.update(kw)
        return "exportateur"

    monkeypatch.setattr(telemetrie, "OTLPSpanExporter", faux)
    return vus


def test_avec_audience_et_credential_la_session_porte_l_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TELEMETRIE_AUDIENCE", "api://underwriting")
    monkeypatch.setattr(telemetrie, "credential_application", lambda *a: _Credential())
    vus = _capturer(monkeypatch)
    telemetrie.creer_exportateur("http://gateway:8000/v1/traces")
    assert _preparer(vus["session"]).headers["Authorization"] == f"Bearer {JETON}"


def test_sans_audience_exportateur_simple(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEMETRIE_AUDIENCE", raising=False)
    vus = _capturer(monkeypatch)
    telemetrie.creer_exportateur("http://localhost:8002/v1/traces")
    assert "session" not in vus
