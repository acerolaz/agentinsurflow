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


# --- S2 : Action Group, règles AL-1 → AL-9, test de disponibilité (faux az) ---

FAUX_AZ = RACINE / "tests/unit/faux_az.sh"
ENV_MIN = {
    "AZURE_RESOURCE_GROUP": "rg",
    "AZURE_LOCATION": "francecentral",
    "LOG_ANALYTICS_WORKSPACE": "law",
    "ALERTE_EMAIL": "ops@exemple.test",
    **{
        f"{n}_STAGING": f"{n.lower()}-s"
        for n in ("APP", "CLUSTER_APP", "RAG_APP", "MCP_APP", "UW_APP", "CALCUL_APP")
    },
}
COMPLET = {
    "PRIX_USD_MILLION": "gpt-x=1.5/6;gpt-y=0.2/0.8",
    "SEUIL_AL8": "10",
    "SEUIL_AL9": "20",
}


def _vigie(tmp_path, nom="journal", **extra):
    journal = tmp_path / nom
    env = {
        "PATH": "/usr/bin:/bin:/opt/homebrew/bin:/usr/local/bin",
        "AZ": str(FAUX_AZ),
        "FAUX_AZ_JOURNAL": str(journal),
        **ENV_MIN,
        **extra,
    }
    env = {k: v for k, v in env.items() if v is not None}
    r = subprocess.run(
        ["bash", str(RACINE / "infra/vigie.sh"), "staging"],
        capture_output=True,
        text=True,
        env=env,
        cwd=RACINE,
    )
    lignes = journal.read_text().splitlines() if journal.exists() else []
    return r, lignes


def _regles(lignes):
    return [li for li in lignes if "scheduled-query create" in li]


def test_sans_alerte_email_le_script_s_arrete(tmp_path):
    r, lignes = _vigie(tmp_path, ALERTE_EMAIL=None)
    assert r.returncode != 0 and "ALERTE_EMAIL" in r.stdout + r.stderr
    assert lignes == []


def test_une_regle_par_ligne_du_catalogue(tmp_path):
    r, lignes = _vigie(tmp_path, **COMPLET)
    assert r.returncode == 0, r.stdout + r.stderr
    regles = _regles(lignes)
    assert len(regles) == 9
    for n in range(1, 10):
        assert any(f"-n al-{n}-staging " in li for li in regles)
    assert any("action-group create" in li and "ag-insurflow-staging" in li for li in lignes)
    assert any(
        "web-test create" in li and "web-sante-staging" in li and "https://gw.exemple/health" in li
        for li in lignes
    )


def test_sans_prix_ni_seuils_trois_regles_sautees(tmp_path):
    r, lignes = _vigie(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert len(_regles(lignes)) == 6
    sortie = r.stdout + r.stderr
    for n in (6, 8, 9):
        assert f"AL-{n} non créée" in sortie


def test_description_cite_alerte_env_et_ancre(tmp_path):
    _, lignes = _vigie(tmp_path, **COMPLET)
    for n in range(1, 10):
        li = next(li for li in _regles(lignes) if f"-n al-{n}-staging " in li)
        desc = li.split("--description ", 1)[1]
        assert f"AL-{n}" in desc and "staging" in desc
        lien = "https://github.com/acerolaz/agentinsurflow/blob/main/docs/exploitation.md"
        assert f"{lien}#al-{n}" in desc


def test_requetes_sans_marqueur_et_prix_substitues(tmp_path):
    _, lignes = _vigie(tmp_path, **COMPLET)
    for li in _regles(lignes):
        assert "$APPI_ID" not in li and "$CLUSTER_APP" not in li and "$PRIX_KQL" not in li
    al6 = next(li for li in _regles(lignes) if "-n al-6-staging " in li)
    assert '"gpt-x",1.5,6,"gpt-y",0.2,0.8,' in al6
    al3 = next(li for li in _regles(lignes) if "-n al-3-staging " in li)
    assert 'ContainerAppName_s == "cluster_app-s"' in al3


def test_noms_stables_entre_deux_lancements(tmp_path):
    _, un = _vigie(tmp_path, "j1", **COMPLET)
    _, deux = _vigie(tmp_path, "j2", **COMPLET)
    assert un == deux and un


def test_chaine_jamais_affichee(tmp_path):
    r, _ = _vigie(tmp_path, **COMPLET)
    assert "chaine-factice" not in r.stdout + r.stderr
