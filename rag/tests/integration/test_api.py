"""Intégration — de la requête HTTP à l'agent, LLM mocké (dependency_overrides)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from agentinsurflow_rag.api import app
from agentinsurflow_rag.api.routes.agent import obtenir_llm
from agentinsurflow_rag.domain.ports import ClientLLM
from fakes import FakeLLM

client = TestClient(app)


@pytest.fixture(autouse=True)
def _sans_vrai_llm() -> Iterator[None]:
    # jamais le vrai Azure OpenAI en test, même si un .env local est chargé
    app.dependency_overrides[obtenir_llm] = lambda: None
    yield
    app.dependency_overrides.clear()


def _brancher(llm: ClientLLM | None) -> None:
    app.dependency_overrides[obtenir_llm] = lambda: llm


def test_health_donne_les_versions_deployees(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_VERSION", "abc123")
    monkeypatch.setenv("APP_RELEASE", "v0.1.1")
    monkeypatch.setenv("APP_MANIFESTE", "0.1.0-build.42")
    reponse = client.get("/health")
    assert reponse.status_code == 200
    assert reponse.json() | {"environnement": None} == {
        "statut": "ok",
        "version": "abc123",
        "release": "v0.1.1",
        "manifeste": "0.1.0-build.42",
        "environnement": None,
    }


def test_l_agent_repond_via_le_llm() -> None:
    _brancher(FakeLLM("Bonjour."))
    reponse = client.post("/api/reponses", json={"texte": "Que couvre le tiers ?"})
    assert reponse.status_code == 200
    assert reponse.json() == {"texte": "Bonjour.", "mode": "llm", "modele": "fake"}


def test_sans_llm_l_agent_repond_en_mode_degrade() -> None:
    _brancher(None)
    assert client.post("/api/reponses", json={"texte": "Question"}).json()["mode"] == "degrade"


def test_question_vide_refusee() -> None:
    assert client.post("/api/reponses", json={"texte": ""}).status_code == 422


def test_l_interface_swagger_est_servie_a_la_racine() -> None:
    assert "swagger-ui" in client.get("/").text
    assert "/api/reponses" in client.get("/openapi.json").json()["paths"]


def test_contrat_rest_plus_de_route_rpc() -> None:
    # S3-24 : ressource au pluriel ; l'ancien nom du sprint 2 n'est plus servi
    assert client.post("/api/agent", json={"texte": "Question"}).status_code == 404
    assert set(client.get("/openapi.json").json()["paths"]) == {"/health", "/api/reponses"}


def test_openapi_sans_servers_pour_la_page_swagger_de_la_gateway() -> None:
    # Servi par la gateway en /rag/openapi.json : sans « servers », le « Try it out » vise la
    # gateway elle-même (/api/reponses, avec jeton, rôle et limite de débit), pas /rag/…
    document = client.get("/openapi.json", headers={"X-Forwarded-Prefix": "/rag"}).json()
    assert "servers" not in document
