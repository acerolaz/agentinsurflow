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
    assert "/v1/souscriptions/{numero_contrat}/evaluation" in contrat["paths"]
    assert contrat["components"]["securitySchemes"], "authentification absente du contrat"
