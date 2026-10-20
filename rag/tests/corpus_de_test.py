"""Petit corpus de fixture (4 articles du Code des assurances, textes abrégés) pour TU et TI."""

from __future__ import annotations

from typing import Any

SHA = "f" * 64


def article(
    doc_id: str, numero: str, texte: str, *, version: str | None = None, **autres: Any
) -> dict[str, Any]:
    return {
        "doc_id": doc_id,
        "version": version or f"{doc_id}-v1",
        "article": numero,
        "date_debut": "2003-01-01",
        "etat": "VIGUEUR",
        "texte_html": f"<p>{texte}</p>",
        "url_source": f"https://www.legifrance.gouv.fr/codes/article_lc/{doc_id}",
    } | autres


CORPUS = [
    article(
        "LEGIARTI000006800836",
        "L. 211-1",
        "Toute personne physique ou morale dont la responsabilité civile peut être engagée en "
        "raison de dommages subis par des tiers du fait d'un véhicule terrestre à moteur doit "
        "être couverte par une assurance obligatoire.",
    ),
    article(
        "LEGIARTI000006800900",
        "L. 211-2",
        "Le contrat d'assurance doit couvrir la responsabilité civile du souscripteur, du "
        "propriétaire du véhicule et de toute personne ayant la garde ou la conduite.",
    ),
    article(
        "LEGIARTI000006801000",
        "A. 121-1",
        "Le coefficient de réduction majoration, appelé bonus malus, est appliqué à la prime de "
        "référence à chaque échéance annuelle du contrat.",
    ),
    article(
        "LEGIARTI000006801100",
        "R. 211-45",
        "La franchise reste à la charge de l'assuré et ne peut être opposée aux victimes ou à "
        "leurs ayants droit.",
    ),
]
