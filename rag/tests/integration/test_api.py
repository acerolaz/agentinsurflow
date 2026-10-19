"""Intégration — contrat HTTP de l'API rag : santé, Swagger, ressources REST et leurs erreurs.

Le parcours de l'agent (``POST /api/reponses``) est dans ``test_reponses_api.py``.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agentinsurflow_rag.api import app

client = TestClient(app)


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


def test_l_interface_swagger_est_servie_a_la_racine() -> None:
    assert "swagger-ui" in client.get("/").text
    assert "/api/reponses" in client.get("/openapi.json").json()["paths"]


ROUTES_REST = {
    "/health",
    "/api/reponses",
    "/api/ingestions",
    "/api/ingestions/{ingestion_id}",
    "/api/extraits",
    "/api/documents/{doc_id}",
}


def test_contrat_rest_plus_de_route_rpc() -> None:
    # S3-24 : ressources au pluriel ; les anciens noms (sprint 2, brief) ne sont plus servis
    assert client.post("/api/agent", json={"texte": "Question"}).status_code == 404
    assert client.post("/v1/ingestion", json={}).status_code == 404
    assert set(client.get("/openapi.json").json()["paths"]) == ROUTES_REST


@pytest.mark.parametrize(
    ("chemin", "methode", "codes"),
    [
        ("/api/reponses", "post", {"200", "401", "403", "404", "422", "503"}),
        ("/api/ingestions", "post", {"201", "401", "403", "422", "503"}),
        ("/api/ingestions", "get", {"200", "401", "403"}),
        ("/api/ingestions/{ingestion_id}", "get", {"200", "401", "403", "404"}),
        ("/api/extraits", "get", {"200", "401", "403", "422", "503"}),
        ("/api/documents/{doc_id}", "get", {"200", "401", "403", "404"}),
    ],
)
def test_chaque_route_documente_ses_erreurs(chemin: str, methode: str, codes: set[str]) -> None:
    operation = client.get("/openapi.json").json()["paths"][chemin][methode]
    assert codes <= set(operation["responses"])
    assert operation["security"]


def test_openapi_sans_servers_pour_la_page_swagger_de_la_gateway() -> None:
    # Servi par la gateway en /rag/openapi.json : sans « servers », le « Try it out » vise la
    # gateway elle-même (/api/reponses, avec jeton, rôle et limite de débit), pas /rag/…
    document = client.get("/openapi.json", headers={"X-Forwarded-Prefix": "/rag"}).json()
    assert "servers" not in document
