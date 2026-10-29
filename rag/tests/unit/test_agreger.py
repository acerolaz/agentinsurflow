"""Unitaires — agrégation des sources en un jeu unique."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agentinsurflow_rag.cli.agreger import agreger, ecrire_jeu, normaliser
from agentinsurflow_rag.cli.ingest import ErreurEnvoi, sha_articles
from agentinsurflow_rag.domain.corpus import normaliser_numero

RACINE = Path(__file__).resolve().parents[3]
NOTICES = RACINE / "rag/corpus/notices_produits"
PROCEDURES = RACINE / "rag/corpus/procedures_internes"
VERSIONNE = RACINE / "data/aggregated/corpus-2026-10-27.json"
TEXTE = "<p>Toute personne physique ou morale doit être assurée.</p>"


def brut(**valeurs: Any) -> dict[str, Any]:
    return {
        "doc_id": "LEGIARTI000006800836",
        "version": "LEGIARTI000006800836",
        "article": "L. 211-1",
        "date_debut": "2003-01-01",
        "etat": "VIGUEUR",
        "texte_html": TEXTE,
        "url_source": "https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000006800836",
    } | valeurs


def dernier(prefixe: str) -> Path:
    return sorted((RACINE / "data/raw").glob(f"{prefixe}-*.json"))[-1]


def instantane(dossier: Path, articles: list[dict[str, Any]]) -> Path:
    chemin = dossier / "code-assurances-2026-10-27.json"
    manifeste = {"date": "2026-10-27", "sha256": sha_articles(articles)}
    chemin.write_text(json.dumps({"manifeste": manifeste, "articles": articles}), encoding="utf-8")
    return chemin


def test_abroge_conserve_etat_d_origine() -> None:
    assert normaliser(brut(etat=" abroge "))["etat"] == "ABROGE"  # type: ignore[index]


def test_abroge_a_date_malformee_ecarte() -> None:
    assert normaliser(brut(etat="ABROGE", date_debut="31/12/2003")) == "date_invalide"


@pytest.mark.parametrize(
    ("champ", "raison"), [("texte_html", "partiel:texte_html"), ("etat", "partiel:etat")]
)
def test_partiel_ecarte(champ: str, raison: str) -> None:
    assert normaliser(brut(**{champ: ""})) == raison


def test_formats_homogeneises() -> None:
    e = normaliser(brut(article=" l 211-1 ", date_debut="2026-10-26T00:00:00"))
    assert isinstance(e, dict)
    assert (e["article"], e["date_debut"]) == (normaliser_numero(" l 211-1 "), "2026-10-26")
    assert e["texte_html"] == brut()["texte_html"]  # HTML d'origine, pas le texte converti


def test_doc_id_en_double_refuse(tmp_path: Path) -> None:
    notices = tmp_path / "notices"
    notices.mkdir()
    for nom in ("a.md", "b.md"):
        (notices / nom).write_text(
            "---\ndoc_id: NOTICE-X\nversion: v1\narticle: N-1\ndate_debut: 2026-01-01\n---\n"
            "Une notice suffisamment longue pour passer la porte de qualité du pipeline.\n",
            encoding="utf-8",
        )
    legifrance = instantane(tmp_path, [brut()])
    with pytest.raises(ErreurEnvoi, match="NOTICE-X"):
        agreger(legifrance, dernier("bareme"), notices, PROCEDURES)


def test_ecart_consigne_dans_le_manifeste(tmp_path: Path) -> None:
    vide = brut(doc_id="LEGIARTI000000000001", texte_html="")
    legifrance = instantane(tmp_path, [brut(), vide])
    jeu = agreger(legifrance, dernier("bareme"), NOTICES, PROCEDURES)
    assert "LEGIARTI000000000001" not in {e["doc_id"] for e in jeu["entrees"]}
    assert jeu["manifeste"]["ecarts"] == [
        {"doc_id": "LEGIARTI000000000001", "source": "legifrance", "raison": "partiel:texte_html"}
    ]


def test_bareme_altere_refuse(tmp_path: Path) -> None:
    contenu = json.loads(dernier("bareme").read_text(encoding="utf-8"))
    contenu["regles"][0]["motif"] = "motif modifié après coup"  # sha du manifeste inchangé
    bareme = tmp_path / "bareme-altere.json"
    bareme.write_text(json.dumps(contenu), encoding="utf-8")
    with pytest.raises(ErreurEnvoi, match="altéré"):
        agreger(dernier("code-assurances"), bareme, NOTICES, PROCEDURES)


def test_sources_reelles_volumes_et_identite(tmp_path: Path) -> None:
    jeu = agreger(dernier("code-assurances"), dernier("bareme"), NOTICES, PROCEDURES)
    assert jeu["manifeste"]["par_source"] == {"legifrance": 119, "redige": 4, "bareme": 6}
    assert jeu["manifeste"]["ecarts"] == []
    assert sum(e["etat"] == "ABROGE" for e in jeu["entrees"]) >= 11
    assert ecrire_jeu(jeu, tmp_path).read_bytes() == VERSIONNE.read_bytes()
