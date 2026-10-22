"""Unitaires — l'exportateur OTLP pose le jeton d'application, sans jamais le journaliser."""

from __future__ import annotations

import logging

import pytest

from agentinsurflow_mcp.infrastructure.otel import telemetrie


class _Jeton:
    token = "jeton-secret-xyz"


class _Credential:
    def __init__(self) -> None:
        self.portees: list[str] = []

    def get_token(self, portee: str) -> _Jeton:
        self.portees.append(portee)
        return _Jeton()


def test_export_porte_le_bearer_et_ne_journalise_pas(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    cred = _Credential()
    exp = telemetrie.ExportateurAuthentifie(
        cred, "api://underwriting", endpoint="http://gateway:8000/v1/traces"
    )
    monkeypatch.setattr(telemetrie.OTLPSpanExporter, "export", lambda self, spans: "ok")
    with caplog.at_level(logging.DEBUG):
        assert exp.export([]) == "ok"
    assert exp._client._headers["Authorization"] == "Bearer jeton-secret-xyz"
    assert cred.portees == ["api://underwriting/.default"]
    assert "jeton-secret-xyz" not in caplog.text


def test_sans_audience_pas_d_authorization(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEMETRIE_AUDIENCE", raising=False)
    exp = telemetrie.creer_exportateur("http://localhost:8002/v1/traces")
    assert type(exp) is telemetrie.OTLPSpanExporter
    assert "Authorization" not in exp._client._headers
