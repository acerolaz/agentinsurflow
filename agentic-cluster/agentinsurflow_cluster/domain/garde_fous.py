"""Garde-fous purs : comparent la sortie d'un agent à la référence, renvoient les codes violés.

Convention de citation (GF4, GF5, GF6) : une citation est le `doc_id` d'un résultat de
`search_rag` (sans `#article`) ; les sources sont les dicts de ces résultats.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation

from .models import Fiche, Pieces, Prime, Risque
from .pii import pii_detectees

COLLECTION_NOTICES = "notices_produits"
_NOMBRE = re.compile(r"\d+(?:[.,]\d+)?")


def _montant(texte: str) -> Decimal | str:
    try:
        return Decimal(texte)
    except InvalidOperation:
        return texte


def gp(
    rapport_pieces: Pieces,
    reference: Pieces,
    exigees: Iterable[str],
    connues: Iterable[str] = (),
    relance_envoyee: bool = False,
) -> list[str]:
    """GP1–GP4. `exigees` : pièces de la formule ; `connues` : tous les types de pièces."""
    codes: list[str] = []
    note = rapport_pieces.note
    if rapport_pieces.statut != reference.statut or set(rapport_pieces.manquantes) != set(
        reference.manquantes
    ):
        codes.append("GP1")
    # En 7a aucune relance n'est envoyée : la note doit nommer chaque pièce manquante.
    if (
        reference.statut == "incomplet"
        and not relance_envoyee
        and not all(m in note for m in reference.manquantes)
    ):
        codes.append("GP2")
    if pii_detectees(note):
        codes.append("GP3")
    exigees = set(exigees)
    if any(c in note for c in set(connues) - exigees):
        codes.append("GP4")
    return codes


def gr(risque: Risque, reference: Risque) -> list[str]:
    """GR1–GR3 : la note cite règles et barème, et n'invente aucun nombre."""
    codes: list[str] = []
    if (risque.score, risque.classe, risque.regle_ids, risque.version_bareme) != (
        reference.score,
        reference.classe,
        reference.regle_ids,
        reference.version_bareme,
    ):
        codes.append("GR1")
    note = risque.note
    if not all(r in note for r in (*reference.regle_ids, reference.version_bareme)):
        codes.append("GR2")
    # Hors identifiants de référence (regle_id, version), seul le score est un nombre permis.
    nue = note
    for ident in (reference.version_bareme, *reference.regle_ids):
        nue = nue.replace(ident, " ")
    if any(n != str(reference.score) for n in _NOMBRE.findall(nue)) or pii_detectees(note):
        codes.append("GR3")
    return codes


def gf(
    fiche: Fiche,
    risque: Risque,
    sources: Iterable[dict[str, object]],
    formule: str,
) -> list[str]:
    """GF1–GF7.

    GF6 : seule l'appartenance du contrat type à `notices_produits` est vérifiée ; sa
    correspondance à la `formule` est 🔴 P13 (non tranchée) : `formule` n'est pas utilisée.
    """
    sources = list(sources)
    codes: list[str] = []
    if (
        fiche.decision not in ("ACCEPTE", "REFUSE", "REVUE_HUMAINE")
        or not fiche.contrat_type
        or not fiche.motifs
        or not fiche.version_bareme
    ):
        codes.append("GF1")
    attendue = {"acceptable": "ACCEPTE", "refus": "REFUSE"}.get(risque.classe)
    if attendue and fiche.decision != attendue:
        codes.append("GF2")
    if (fiche.score, fiche.version_bareme, fiche.regle_ids) != (
        risque.score,
        risque.version_bareme,
        risque.regle_ids,
    ):
        codes.append("GF3")
    doc_ids = {s["doc_id"] for s in sources}
    if not fiche.citations or not set(fiche.citations) <= doc_ids:
        codes.append("GF4")
    if fiche.decision == "REFUSE" and not any(
        s["doc_id"] in fiche.citations and s.get("regle_id") in risque.regle_ids for s in sources
    ):
        codes.append("GF5")
    if fiche.decision == "ACCEPTE" and not any(
        s["collection"] == COLLECTION_NOTICES and s["doc_id"] == fiche.contrat_type for s in sources
    ):
        codes.append("GF6")
    if any(pii_detectees(m) for m in fiche.motifs):
        codes.append("GF7")
    return codes


def ga(prime: Prime, reference: Prime) -> list[str]:
    """GA1–GA3 : montants et version de la référence ; version citée ; aucune donnée personnelle."""
    codes: list[str] = []
    if any(
        _montant(a) != _montant(b)
        for a, b in (
            (prime.prime_ttc_annuelle, reference.prime_ttc_annuelle),
            (prime.prime_mensuelle, reference.prime_mensuelle),
        )
    ):
        codes.append("GA1")
    if prime.version_formule != reference.version_formule or (
        reference.version_formule not in prime.explication
    ):
        codes.append("GA2")
    if pii_detectees(prime.explication):
        codes.append("GA3")
    return codes
