"""Instantané versionné du barème : le fichier de data/raw suit le code."""

from pathlib import Path

from agentinsurflow_calcul.domain.bareme import VERSION_BAREME
from agentinsurflow_calcul.instantane import ecrire, serialiser

RACINE = Path(__file__).resolve().parents[3]
VERSIONNE = RACINE / "data/raw" / f"{VERSION_BAREME}.json"


def test_instantane_versionne_existe_pour_la_version_du_code():
    assert VERSIONNE.exists(), "lancer « make bareme » et versionner le fichier"


def test_regenere_identique_au_versionne(tmp_path):
    assert ecrire(tmp_path).read_bytes() == VERSIONNE.read_bytes()


def test_manifeste_et_seuils_en_texte():
    contenu = serialiser()
    assert contenu["manifeste"]["regles"] == 6
    assert contenu["manifeste"]["date_debut"] == "2026-10-26"
    assert contenu["regles"][2]["conditions"] == [
        {"champ": "crm", "operateur": ">", "seuil": "1.25"}
    ]
