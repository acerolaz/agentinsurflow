"""D22 : rag lit les dossiers par la gateway (:8000), jamais en direct (:8002)."""

import json
from pathlib import Path

import yaml

from agentinsurflow_rag.infrastructure.entra.obo import ConfigObo

RACINE = Path(__file__).resolve().parents[2]


def _env(conteneur: dict, nom: str) -> str:
    return next(v["value"] for v in conteneur["env"] if v["name"] == nom)


def test_defaut_du_code_vise_la_gateway():
    assert ConfigObo.model_fields["underwriting_url"].default == "http://localhost:8000"


def test_azure_vise_la_gateway():
    # #70 : rag a sa Container App et joint la gateway par son FQDN
    modele = yaml.safe_load((RACINE / "infra/containerapp-rag.yaml").read_text())
    rag = next(c for c in modele["properties"]["template"]["containers"] if c["name"] == "rag")
    assert _env(rag, "UNDERWRITING_URL") == "${GATEWAY_URL}"
    assert _env(rag, "AZURE_OPENAI_ENDPOINT") == "${GATEWAY_URL}/api/llm"
    principale = yaml.safe_load((RACINE / "infra/containerapp.yaml").read_text())
    assert all(c["name"] != "rag" for c in principale["properties"]["template"]["containers"])


def test_compose_vise_la_gateway():
    compose = yaml.safe_load((RACINE / "docker-compose.yml").read_text())
    assert compose["services"]["rag"]["environment"]["UNDERWRITING_URL"] == "http://gateway:8000"


def test_la_gateway_route_les_contrats_vers_underwriting_admin():
    routes = next((RACINE / "gateway/src").glob("*/appsettings.Routes.json"))
    route = json.loads(routes.read_text())["ReverseProxy"]["Routes"]["underwriting-contrats"]
    assert route["Match"]["Path"] == "/api/contrats/{**reste}"
    assert route["ClusterId"] == "underwriting"
    assert route["AuthorizationPolicy"] == "underwriting-gestionnaire"
