"""Unitaires — règles du pipeline d'ingestion et de la porte de pertinence (fonctions pures)."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from agentinsurflow_rag.domain.corpus import (
    TEXTE_MIN,
    collections_pour,
    decider,
    decouper,
    hash_contenu,
    html_vers_texte,
    nettoyer,
    normaliser_numero,
    passe_la_porte,
    references_articles,
)
from agentinsurflow_rag.domain.models import ArticlePropre, Rejet

TEXTE = "<p>Toute personne physique ou morale doit être assurée.</p>"


def _brut(**valeurs: Any) -> dict[str, Any]:
    return {
        "doc_id": "LEGIARTI000006800836",
        "version": "LEGIARTI000006800836",
        "article": "L. 211-1",
        "date_debut": "2003-01-01",
        "etat": "VIGUEUR",
        "texte_html": TEXTE,
        "url_source": "https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000006800836",
    } | valeurs


# ---------------------------------------------------------------- numéros d'articles


@pytest.mark.parametrize(
    ("brut", "attendu"),
    [
        ("L. 211-1", "L211-1"),
        ("l211-1", "L211-1"),
        ("R. 211-45", "R211-45"),
        ("A121-1 ", "A121-1"),
        ("L 121-12-1", "L121-12-1"),
        ("d.  211-2", "D211-2"),
    ],
)
def test_normaliser_numero(brut: str, attendu: str) -> None:
    assert normaliser_numero(brut) == attendu


@pytest.mark.parametrize(
    "question", ["que dit l'article L. 211-1 ?", "l211-1", "Article L211-1.", "(L 211-1)"]
)
def test_references_articles_variantes(question: str) -> None:
    assert references_articles(question) == ["L211-1"]


def test_references_articles_plusieurs_sans_doublon_dans_l_ordre() -> None:
    assert references_articles("R211-45, puis L121-1 et encore R. 211-45") == [
        "R211-45",
        "L121-1",
    ]


@pytest.mark.parametrize("question", ["Que couvre la garantie tiers ?", "le 211-1", "L211"])
def test_sans_reference_d_article(question: str) -> None:
    assert references_articles(question) == []


# ---------------------------------------------------------------- HTML → texte


def test_html_vers_texte_retire_balises_et_espaces() -> None:
    assert html_vers_texte("<p>A&nbsp; b</p><p>c</p>") == "A b\nc"


def test_html_vers_texte_entites_et_normalisation_nfc() -> None:
    # « e » + accent combinant → « é » précomposé (NFC)
    assert html_vers_texte("<p>assur&eacute;e et assurée &amp; co</p>") == "assurée et assurée & co"


def test_html_vers_texte_listes_un_element_par_ligne() -> None:
    assert html_vers_texte("<ul><li>1° le tiers ;</li><li>2° le vol.</li></ul>") == (
        "1° le tiers ;\n2° le vol."
    )


def test_html_vers_texte_tableaux_une_ligne_par_rangee() -> None:
    html = "<table><tr><td>Classe</td><td>Taux</td></tr><tr><td>A</td><td>0,5 %</td></tr></table>"
    assert html_vers_texte(html) == "Classe Taux\nA 0,5 %"


def test_html_vers_texte_br_et_lignes_vides() -> None:
    assert html_vers_texte("un<br/>deux<br><br>   <div>trois</div>") == "un\ndeux\ntrois"


# ---------------------------------------------------------------- nettoyage


def test_nettoyer_article_valide() -> None:
    propre = nettoyer(_brut())
    assert isinstance(propre, ArticlePropre)
    assert propre.article == "L211-1"
    assert propre.date_debut == date(2003, 1, 1)
    assert propre.texte == "Toute personne physique ou morale doit être assurée."
    assert propre.hash_contenu == hash_contenu(propre.texte)


@pytest.mark.parametrize(
    "champ", ["doc_id", "version", "article", "etat", "texte_html", "url_source"]
)
def test_nettoyer_rejette_partiel(champ: str) -> None:
    rejet = nettoyer({k: v for k, v in _brut().items() if k != champ})
    assert rejet == Rejet(
        doc_id=None if champ == "doc_id" else "LEGIARTI000006800836", raison=f"partiel:{champ}"
    )


def test_nettoyer_recopie_regle_id() -> None:
    propre = nettoyer(_brut(regle_id="R01_SUSPENSION"))
    assert isinstance(propre, ArticlePropre) and propre.regle_id == "R01_SUSPENSION"


def test_nettoyer_sans_regle_id_garde_le_hash_du_texte() -> None:
    propre = nettoyer(_brut())
    assert isinstance(propre, ArticlePropre) and propre.regle_id is None
    assert propre.hash_contenu == hash_contenu(propre.texte)


def test_regle_id_change_le_hash() -> None:
    # même texte, autre règle : la dédup doit le voir (sinon l'ancien regle_id resterait)
    a = nettoyer(_brut(regle_id="R01_SUSPENSION"))
    b = nettoyer(_brut(regle_id="R02_RESILIATIONS"))
    assert isinstance(a, ArticlePropre) and isinstance(b, ArticlePropre)
    assert a.hash_contenu != b.hash_contenu


def test_nettoyer_champ_vide_est_partiel() -> None:
    assert nettoyer(_brut(url_source="  ")) == Rejet("LEGIARTI000006800836", "partiel:url_source")


def test_nettoyer_rejette_vide() -> None:
    assert nettoyer(_brut(texte_html="<p> </p><br/>")).raison == "vide"  # type: ignore[union-attr]


def test_nettoyer_rejette_trop_court() -> None:
    court = "x" * (TEXTE_MIN - 1)
    assert nettoyer(_brut(texte_html=f"<p>{court}</p>")).raison == "trop_court"  # type: ignore[union-attr]
    assert isinstance(nettoyer(_brut(texte_html="x" * TEXTE_MIN)), ArticlePropre)


def test_nettoyer_rejette_abroge() -> None:
    assert nettoyer(_brut(etat="ABROGE")).raison == "non_en_vigueur:ABROGE"  # type: ignore[union-attr]


def test_nettoyer_rejette_date_invalide() -> None:
    assert nettoyer(_brut(date_debut="31/12/2003")).raison == "date_invalide"  # type: ignore[union-attr]


def test_nettoyer_sans_date_de_debut() -> None:
    propre = nettoyer(_brut(date_debut=None))
    assert isinstance(propre, ArticlePropre) and propre.date_debut is None


# ---------------------------------------------------------------- dédup et versions


def test_decider() -> None:
    assert decider(None, "v1", "h") == "nouveau"
    assert decider(("v1", "h"), "v1", "h") == "inchange"
    assert decider(("v1", "h"), "v2", "h") == "inchange"  # même contenu : rien à réindexer
    assert decider(("v1", "h"), "v2", "h2") == "nouvelle_version"


def test_decider_contenu_modifie_sous_la_meme_version() -> None:
    # (doc_id, version) est unique en base : on signale au lieu d'écraser en silence
    assert decider(("v1", "h"), "v1", "h2") == "conflit_version"


def test_hash_contenu_sha256_hexa() -> None:
    assert hash_contenu("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


# ---------------------------------------------------------------- découpage


def test_decouper_article_court_un_seul_chunk() -> None:
    assert decouper("x" * 1999) == ["x" * 1999]
    assert decouper("x" * 2000) == ["x" * 2000]


def test_decouper_article_long_recouvrement() -> None:
    paragraphes = [c * 1200 for c in "abc"]
    chunks = decouper("\n".join(paragraphes))
    assert len(chunks) >= 2
    assert all(len(c) <= 2000 for c in chunks)
    for precedent, suivant in zip(chunks, chunks[1:], strict=False):
        assert suivant.startswith(precedent[-200:])
    assert all(any(p in c for c in chunks) for p in paragraphes)


def test_decouper_paragraphe_geant_redecoupe() -> None:
    chunks = decouper("y" * 5000)
    assert len(chunks) >= 3
    assert all(len(c) <= 2000 for c in chunks)
    assert (
        "".join(c[200:] if i else c for i, c in enumerate(chunks)).replace("\n", "") == "y" * 5000
    )


# ---------------------------------------------------------------- porte de pertinence


def test_porte() -> None:
    assert passe_la_porte(None, True, 0.5)  # référence exacte : passe sans cosinus
    assert not passe_la_porte(0.49, False, 0.5)
    assert passe_la_porte(0.5, False, 0.5)  # borne incluse
    assert not passe_la_porte(None, False, 0.0)  # base vide : rien ne passe


@pytest.mark.parametrize(
    ("cosinus", "seuil", "attendu"), [(1.0, 1.0, True), (0.0, 0.0, True), (0.999, 1.0, False)]
)
def test_porte_bornes_du_seuil(cosinus: float, seuil: float, attendu: bool) -> None:
    assert passe_la_porte(cosinus, False, seuil) is attendu


# ---------------------------------------------------------------- collections par rôle


def test_gestionnaire_lit_les_trois_collections() -> None:
    assert collections_pour(frozenset({"Gestionnaire"})) == [
        "notices_produits",
        "procedures_internes",
        "textes_reglementaires",
    ]


def test_role_absent_ne_lit_rien() -> None:
    assert collections_pour(frozenset({"Ingestion"})) == []
