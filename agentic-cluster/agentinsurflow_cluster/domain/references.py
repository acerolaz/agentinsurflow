"""Références déterministes : ce que les outils (Function de calcul, pièces) établissent.

Les agents rédigent des notes ; les garde-fous les comparent à ces références.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from .models import Pieces, Prime, Risque

RELEVE = "releve_information"
MOIS_RELEVE_MAX = 3  # D85 : relevé d'information daté d'au plus 3 mois avant la date d'effet


def _moins_mois(jour: date, mois: int) -> date:
    annee, m = divmod(jour.year * 12 + jour.month - 1 - mois, 12)
    return _borne(annee, m + 1, jour.day)


def _borne(annee: int, mois: int, jour: int) -> date:
    """Le jour demandé, ramené à la fin du mois s'il n'existe pas (31 → 30, 29 février…)."""
    while True:
        try:
            return date(annee, mois, jour)
        except ValueError:
            jour -= 1


def verifier_completude(
    formule: str,
    pieces: list[dict[str, str]],
    date_effet: date,
    exigees: Mapping[str, tuple[str, ...]],
) -> Pieces:
    """Pièces exigées pour la `formule` absentes ou périmées (relevé > 3 mois avant l'effet)."""
    limite = _moins_mois(date_effet, MOIS_RELEVE_MAX)
    presentes = {p["type"]: date.fromisoformat(p["date_emission"]) for p in pieces}
    manquantes = tuple(
        type_
        for type_ in exigees[formule]
        if type_ not in presentes or (type_ == RELEVE and presentes[type_] < limite)
    )
    if not manquantes:
        return Pieces("complet", (), "Toutes les pièces exigées sont présentes.")
    return Pieces("incomplet", manquantes, "Pièces manquantes : " + ", ".join(manquantes) + ".")


def risque_de(resultat_evaluer: dict[str, object]) -> Risque:
    """Référence de risque, tirée du retour de `evaluer_risque` (la note est laissée vide)."""
    regles: list[dict[str, str]] = resultat_evaluer["regles"]  # type: ignore[assignment]
    return Risque(
        score=int(resultat_evaluer["score"]),  # type: ignore[call-overload]
        classe=resultat_evaluer["classe"],  # type: ignore[arg-type]
        regle_ids=tuple(r["regle_id"] for r in regles),
        version_bareme=str(resultat_evaluer["version_bareme"]),
        note="",
    )


def prime_de(resultat_calculer: dict[str, object]) -> Prime:
    """Référence de prime, tirée du retour de `calculer_prime` (l'explication est laissée vide)."""
    return Prime(
        prime_ttc_annuelle=str(resultat_calculer["prime_ttc_annuelle"]),
        prime_mensuelle=str(resultat_calculer["prime_mensuelle"]),
        version_formule=str(resultat_calculer["version_formule"]),
        explication="",
    )
