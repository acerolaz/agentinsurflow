"""Procédures internes générées depuis l'instantané du barème (#99)."""

import json
from pathlib import Path

import pytest

from agentinsurflow_rag.cli.ingest import URL_DEPOT, lire_en_tete
from agentinsurflow_rag.domain.procedures import ErreurProcedures, condition_lisible, generer

BAREME = {
    "manifeste": {"version_bareme": "bareme-test", "date_debut": "2026-10-26"},
    "regles": [
        {
            "regle_id": "R03_CRM",
            "libelle": "CRM élevé",
            "motif": "Le CRM dépasse 1,25.",
            "effet": "REFUSE",
            "conditions": [{"champ": "crm", "operateur": ">", "seuil": "1.25"}],
        }
    ],
}


def test_generer_champs_et_texte():
    [doc] = generer(BAREME, {"R03_CRM": "## Décision\nBarème {version_bareme}."}, "https://x")
    assert (doc["doc_id"], doc["version"], doc["article"], doc["date_debut"], doc["regle_id"]) == (
        "PI-R03_CRM",
        "PI-R03_CRM-bareme-test",
        "PI-R03-CRM",
        "2026-10-26",
        "R03_CRM",
    )
    assert doc["etat"] == "VIGUEUR"
    assert doc["url_source"] == "https://x/procedures_internes/R03_CRM.md"
    assert "Condition : `crm` plus de 1,25." in doc["texte_html"]
    assert "Motif retenu par le barème : « Le CRM dépasse 1,25. »" in doc["texte_html"]
    assert doc["texte_html"].endswith("## Décision\nBarème bareme-test.")


def test_condition_composee():
    assert (
        condition_lisible(
            [
                {"champ": "a", "operateur": "<", "seuil": "36"},
                {"champ": "b", "operateur": ">", "seuil": "7"},
            ]
        )
        == "`a` moins de 36 et `b` plus de 7"
    )


@pytest.mark.parametrize("rediges", [{}, {"R03_CRM": "x", "R99_X": "y"}, {"R03_CRM": "{inconnu}"}])
def test_incoherence_leve_une_erreur_qui_nomme_la_regle(rediges):
    with pytest.raises(ErreurProcedures, match="R03_CRM|R99_X"):
        generer(BAREME, rediges, "https://x")


def test_corpus_reel_un_document_par_regle_id():
    racine = Path(__file__).resolve().parents[3]
    dernier = sorted((racine / "data/raw").glob("bareme-*.json"))[-1]
    bareme_reel = json.loads(dernier.read_text(encoding="utf-8"))
    rediges_reels = {}
    for fichier in (racine / "rag/corpus/procedures_internes").glob("*.md"):
        en_tete, corps = lire_en_tete(fichier)
        rediges_reels[en_tete["regle_id"]] = corps
    docs = generer(bareme_reel, rediges_reels, URL_DEPOT)
    assert [d["regle_id"] for d in docs] == [r["regle_id"] for r in bareme_reel["regles"]]
    assert len({d["doc_id"] for d in docs}) == 6
    assert all("{" not in d["texte_html"] for d in docs)
