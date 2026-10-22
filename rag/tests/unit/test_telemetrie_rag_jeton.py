"""Unitaires — l'exportateur OTLP de rag pose le jeton d'application, sans jamais le journaliser."""

from __future__ import annotations

import logging
from typing import Any

import pytest
import requests
from azure.core.exceptions import ClientAuthenticationError
from azure.identity import ClientAssertionCredential

from agentinsurflow_rag.infrastructure.entra.application import credential_application
from agentinsurflow_rag.infrastructure.otel import telemetrie

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
    assert "ClientAuthenticationError" not in caplog.text  # pas de type d'exception détaillé
    assert "indisponible" in caplog.text
    assert JETON not in caplog.text


def _espion(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    vus: dict[str, Any] = {}

    def faux(**kwargs: Any) -> object:
        vus.update(kwargs)
        return object()

    monkeypatch.setattr(telemetrie, "OTLPSpanExporter", faux)
    return vus


def test_sans_audience_l_exportateur_n_a_pas_de_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEMETRIE_AUDIENCE", raising=False)
    vus = _espion(monkeypatch)
    telemetrie.creer_exportateur("http://localhost:8002/v1/traces")
    assert "session" not in vus


def test_avec_audience_et_secret_local_la_session_porte_l_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for nom, valeur in {
        "TELEMETRIE_AUDIENCE": "api://u",
        "AZURE_TENANT_ID": "t",
        "RAG_API_CLIENT_ID": "c",
        "RAG_CLIENT_SECRET": "s",
    }.items():
        monkeypatch.setenv(nom, valeur)
    vus = _espion(monkeypatch)
    telemetrie.creer_exportateur("http://gateway:8000/v1/traces")
    assert callable(vus["session"].auth)


def test_identite_managee_sans_secret_la_session_porte_l_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for nom, valeur in {
        "TELEMETRIE_AUDIENCE": "api://u",
        "AZURE_TENANT_ID": "t",
        "RAG_API_CLIENT_ID": "c",
        "AZURE_UAMI_CLIENT_ID": "uami",
    }.items():
        monkeypatch.setenv(nom, valeur)
    monkeypatch.delenv("RAG_CLIENT_SECRET", raising=False)
    vus = _espion(monkeypatch)
    telemetrie.creer_exportateur("http://gateway:8000/v1/traces")
    assert callable(vus["session"].auth)
    assert isinstance(credential_application("t", "c", None, "uami"), ClientAssertionCredential)


def test_configuration_incomplete_pas_de_credential() -> None:
    assert credential_application(None, "c", "s", None) is None
    assert credential_application("t", "c", None, None) is None
