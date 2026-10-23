"""TU — l'exportateur OTLP du cluster pose le jeton d'application, sans le journaliser.

Même contrat que ``serveur-mcp`` : en Azure (``TELEMETRIE_AUDIENCE``), export par la gateway avec un
jeton d'application de l'inscription du cluster (rôle Telemetrie) ;
en local, export direct sans jeton.
Fournisseur de jeton factice.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
import requests
from azure.core.exceptions import ClientAuthenticationError

from agentinsurflow_cluster.infrastructure.otel import telemetrie

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


def _capturer(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    vus: dict[str, Any] = {}

    def faux(**kw: Any) -> str:
        vus.update(kw)
        return "exportateur"

    monkeypatch.setattr(telemetrie, "OTLPSpanExporter", faux)
    return vus


def _entra(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AZURE_TENANT_ID", "tenant")
    monkeypatch.setenv("INSURFLOW_CLUSTER_CLIENT_ID", "app-cluster")
    monkeypatch.setenv("INSURFLOW_CLIENT_SECRET", "secret-local")


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


def test_avec_audience_la_session_de_l_exportateur_porte_l_autorisation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _entra(monkeypatch)
    monkeypatch.setenv("TELEMETRIE_AUDIENCE", "api://underwriting")
    vus_credential: list[tuple[Any, ...]] = []

    def credential(*args: Any) -> _Credential:
        vus_credential.append(args)
        return _Credential()

    monkeypatch.setattr(telemetrie, "credential_application", credential)
    vus = _capturer(monkeypatch)
    telemetrie.creer_exportateur()
    assert _preparer(vus["session"]).headers["Authorization"] == f"Bearer {JETON}"
    assert vus_credential[0][:2] == ("tenant", "app-cluster")  # l'inscription du cluster


def test_sans_audience_exportateur_simple_sans_jeton(monkeypatch: pytest.MonkeyPatch) -> None:
    _entra(monkeypatch)
    monkeypatch.delenv("TELEMETRIE_AUDIENCE", raising=False)
    vus = _capturer(monkeypatch)
    telemetrie.creer_exportateur()
    assert "session" not in vus


def test_audience_sans_identite_configuree_exportateur_simple(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _entra(monkeypatch)
    monkeypatch.setenv("TELEMETRIE_AUDIENCE", "api://underwriting")
    monkeypatch.setattr(telemetrie, "source_assertion", lambda _cfg: None)
    vus = _capturer(monkeypatch)
    telemetrie.creer_exportateur()
    assert "session" not in vus
