"""TU — ``docs/openapi/agentic-cluster.json`` reste celui que le code génère (C9)."""

from __future__ import annotations

import json
from pathlib import Path

from agentinsurflow_cluster.api import app

FICHIER = Path(__file__).parents[2] / "docs/openapi/agentic-cluster.json"


def test_le_contrat_versionne_est_celui_du_code() -> None:
    assert json.loads(FICHIER.read_text(encoding="utf-8")) == app.openapi(), (
        "contrat périmé : lancer make openapi"
    )


def test_le_contrat_documente_les_routes_et_le_jeton() -> None:
    contrat = json.loads(FICHIER.read_text(encoding="utf-8"))
    evaluation = contrat["paths"]["/api/v1/souscriptions/{numero_contrat}/evaluation"]
    assert set(evaluation) == {"post", "get", "patch"}  # R2/R3 (#243 #244)
    assert {"200", "201"} <= set(evaluation["post"]["responses"])
    decision = contrat["paths"]["/api/v1/souscriptions/{numero_contrat}/evaluation/decision"]
    assert {"200", "201"} <= set(decision["put"]["responses"])
    assert contrat["components"]["securitySchemes"], "authentification absente du contrat"
