"""Intégration — exigence de rôle sur une route (refus par défaut) et erreurs ProblemDetails."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from agentinsurflow_rag.api.erreurs import installer_gestionnaires
from agentinsurflow_rag.api.securite import charger_auth, exiger, obtenir_cle
from agentinsurflow_rag.domain.models import Appelant
from jetons_de_test import CLE_PUBLIQUE, config_auth, creer

app = FastAPI()
installer_gestionnaires(app)


@app.get("/protegee")
def protegee(appelant: Annotated[Appelant, Depends(exiger("Gestionnaire"))]) -> dict[str, str]:
    return {"oid": appelant.oid}


app.dependency_overrides[obtenir_cle] = lambda: CLE_PUBLIQUE
app.dependency_overrides[charger_auth] = config_auth
client = TestClient(app)


def _code(reponse: Any) -> str:
    assert reponse.headers["content-type"].startswith("application/problem+json")
    return str(reponse.json()["code"])


def test_sans_jeton_401_jeton_absent() -> None:
    reponse = client.get("/protegee")
    assert reponse.status_code == 401
    assert _code(reponse) == "JETON_ABSENT"
    assert reponse.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("jeton", ["pas-un-jwt", creer(expire_dans=-120)])
def test_jeton_invalide_401(jeton: str) -> None:
    reponse = client.get("/protegee", headers={"Authorization": f"Bearer {jeton}"})
    assert reponse.status_code == 401
    assert _code(reponse) == "JETON_INVALIDE"


def test_role_manquant_403() -> None:
    reponse = client.get("/protegee", headers={"Authorization": f"Bearer {creer(['Ingestion'])}"})
    assert reponse.status_code == 403
    assert _code(reponse) == "ROLE_MANQUANT"


def test_bon_role_passe() -> None:
    reponse = client.get("/protegee", headers={"Authorization": f"Bearer {creer(oid='oid-z')}"})
    assert reponse.status_code == 200
    assert reponse.json() == {"oid": "oid-z"}


def test_schema_de_securite_dans_l_openapi() -> None:
    document = client.get("/openapi.json").json()
    assert document["components"]["securitySchemes"]
    assert document["paths"]["/protegee"]["get"]["security"]


def test_sans_jeton_401_meme_sans_configuration_entra(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # refus par défaut : l'absence de jeton se juge avant de lire la configuration (sinon 503)
    monkeypatch.chdir(tmp_path)  # aucun .env lu
    monkeypatch.delenv("AZURE_TENANT_ID", raising=False)
    monkeypatch.delenv("RAG_API_CLIENT_ID", raising=False)
    sans_config = FastAPI()
    installer_gestionnaires(sans_config)
    sans_config.get("/protegee")(protegee)
    reponse = TestClient(sans_config).get("/protegee")
    assert (reponse.status_code, _code(reponse)) == (401, "JETON_ABSENT")
