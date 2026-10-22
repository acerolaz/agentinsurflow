"""Entités du domaine : faits du dossier, règles déclenchées, résultat du barème."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal


@dataclass(frozen=True)
class FaitsRisque:
    """Les faits du dossier utiles au barème ; ``None`` = donnée absente."""

    suspensions: int | None
    resiliations: int | None
    crm: Decimal | None
    nb_sinistres_responsables_trois_ans: int | None
    nb_sinistres_trois_ans: int | None
    anciennete_permis_mois: int | None
    puissance_fiscale_cv: int | None


@dataclass(frozen=True)
class RegleDeclenchee:
    """Une règle du barème déclenchée, avec son motif (jamais une valeur du dossier)."""

    regle_id: str
    motif: str


@dataclass(frozen=True)
class ResultatRisque:
    version_bareme: str
    classe: Literal["acceptable", "refus"]
    decision: Literal["ACCEPTE", "REFUSE"]
    score: float
    regles: tuple[RegleDeclenchee, ...]


class DonneeHorsBareme(Exception):
    """Un fait requis manque : le barème ne peut pas conclure."""

    def __init__(self, champ: str) -> None:
        super().__init__(champ)
        self.champ = champ  # le nom du champ, jamais sa valeur


CRM_MIN, CRM_MAX = Decimal("0.50"), Decimal("3.50")  # bornes légales du bonus-malus


def verifier_crm(crm: Decimal | None) -> Decimal:
    if crm is None or not CRM_MIN <= crm <= CRM_MAX:
        raise DonneeHorsBareme("crm")
    return crm


@dataclass(frozen=True)
class FaitsPrime:
    """Les faits utiles à la formule de prime ; ``None`` = donnée absente."""

    formule: str | None
    anciennete_permis_mois: int | None
    departement: str | None
    puissance_fiscale_cv: int | None
    type_usage: str | None
    crm: Decimal | None


@dataclass(frozen=True)
class ResultatPrime:
    version_formule: str
    prime_ht: Decimal
    montant_taxes: Decimal
    prime_ttc_annuelle: Decimal
    prime_mensuelle: Decimal
    coefficients: dict[str, Decimal]
