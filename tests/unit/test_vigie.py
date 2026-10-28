"""Vigie (#54) : chaîne App Insights par secret, exigé au déploiement, `make vigie`."""

import subprocess
from pathlib import Path

import pytest
import yaml

RACINE = Path(__file__).resolve().parents[2]

APPS = [
    "containerapp.yaml",
    "containerapp-cluster.yaml",
    "containerapp-rag.yaml",
    "containerapp-mcp.yaml",
    "containerapp-underwriting.yaml",
]


@pytest.mark.parametrize("fichier", APPS)
def test_chaque_app_lit_la_chaine_app_insights_par_secret(fichier):
    modele = yaml.safe_load((RACINE / "infra" / fichier).read_text())
    for c in modele["properties"]["template"]["containers"]:
        assert {
            "name": "APPLICATIONINSIGHTS_CONNECTION_STRING",
            "secretRef": "appinsights-connection",
        } in c["env"]


def test_deploy_verifie_le_secret_avant_chaque_update():
    texte = (RACINE / ".github/workflows/deploy.yml").read_text()
    assert texte.count('index("appinsights-connection")') == 5


def test_vigie_refuse_un_env_inconnu():
    r = subprocess.run(
        ["bash", str(RACINE / "infra/vigie.sh"), "recette"], capture_output=True, text=True
    )
    assert r.returncode != 0 and "staging|production" in r.stdout + r.stderr
