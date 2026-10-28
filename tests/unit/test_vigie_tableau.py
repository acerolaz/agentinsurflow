"""Vigie (S2, Task 3) : tableau de bord, une tuile par question, objectif écrit."""

import json
import re

import pytest

from tests.unit.test_vigie import COMPLET, RACINE, _vigie

MODELE = RACINE / "infra/vigie/dashboard.json"
KQL = RACINE / "infra/vigie/kql"

QUESTIONS = [
    "Comment lire ce tableau",
    "Le service répond-il ?",
    "Combien de dossiers évalués ?",
    "Combien de temps prend une évaluation ?",
    "Quelle part part en revue humaine, et pourquoi ?",
    "Combien coûte un dossier ?",
    "Les garde-fous bloquent-ils plus que d'habitude ?",
    "Combien d'évaluations sans décision ?",
    "Le modèle de langage est-il disponible ?",
    "Alertes en cours",
]


def _tuiles(modele):
    """(titre, sous-titre, requête ou None) de chaque tuile."""
    for p in modele["properties"]["lenses"][0]["parts"]:
        m = p["metadata"]
        if m["inputs"]:
            e = {i["name"]: i.get("value") for i in m["inputs"]}
            yield e["PartTitle"], e["PartSubTitle"], e["Query"]
        else:
            c = m["settings"]["content"]["settings"]
            yield c["title"], c["subtitle"], None


def _modele():
    return json.loads(MODELE.read_text())


@pytest.mark.parametrize("question", QUESTIONS)
def test_une_tuile_par_question(question):
    assert question in {t for t, _, _ in _tuiles(_modele())}


@pytest.mark.parametrize("objectif", ["30 s", "20 %", "0,15", "1 %", "100 %"])
def test_objectif_ecrit_sur_les_tuiles(objectif):
    assert any(objectif in f"{t} {s}" for t, s, _ in _tuiles(_modele()))


def test_requetes_viennent_des_fichiers():
    requetes = [q for _, _, q in _tuiles(_modele()) if q]
    assert requetes
    for q in requetes:
        assert q.startswith("@kql:") and (KQL / q.removeprefix("@kql:")).is_file(), q


def test_assemblage_sans_placeholder(tmp_path):
    r, journal = _vigie(tmp_path, TMPDIR=str(tmp_path), **COMPLET)
    assert r.returncode == 0, r.stdout + r.stderr
    appel = next(ligne for ligne in journal if "portal dashboard create" in ligne)
    assert "-n vigie-staging" in appel
    assert any("extension add -n portal" in ligne for ligne in journal)
    assert re.search(r"--input-path \S+", appel)
    texte = (tmp_path / "journal.input").read_text()
    json.loads(texte)
    for interdit in (
        "@kql:",
        "$APPI_ID",
        "$CLUSTER_APP",
        "$WORKSPACE_ID",
        "$PRIX_KQL",
        "$ENV",
        "$LOCATION",
    ):
        assert interdit not in texte
    assert "gpt-x" in texte  # le tarif est bien substitué dans la tuile de coût


def test_periode_24h_actualisation_et_types_de_tuile():
    modele = _modele()
    md = modele["properties"]["metadata"]["model"]
    assert md["timeRange"]["value"]["relative"] == {"duration": 24, "timeUnit": 1}
    assert md["refreshInterval"]["value"] == {"interval": 5, "unit": "min"}
    for p in modele["properties"]["lenses"][0]["parts"]:
        m = p["metadata"]
        if m["type"].endswith("LogsDashboardPart"):
            assert {"name": "TimeRange", "value": "PT24H"} in m["inputs"]
        else:
            assert m["type"].endswith("MarkdownPart")
