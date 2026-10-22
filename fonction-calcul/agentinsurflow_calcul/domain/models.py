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
