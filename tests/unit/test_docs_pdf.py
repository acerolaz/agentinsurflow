"""TU — ``tools/docs_pdf.py`` : du Markdown au HTML sémantique d'un PDF accessible (9.10, 11.9…)."""

from __future__ import annotations

from tools.docs_pdf import page_html, titre_de


def test_titre_du_document_est_son_premier_titre() -> None:
    assert titre_de("# Exploitation\n\ntexte") == "Exploitation"


def test_page_declare_la_langue_et_le_titre() -> None:
    html = page_html("# Mon titre\n\nDu texte.")
    assert '<html lang="fr">' in html
    assert "<title>Mon titre</title>" in html


def test_les_tableaux_gardent_leurs_entetes() -> None:
    assert "<th>Colonne</th>" in page_html("# T\n\n| Colonne |\n|---|\n| valeur |\n")


def test_le_contenu_du_titre_est_echappe() -> None:
    assert "<title>A &lt; B</title>" in page_html("# A < B\n")
