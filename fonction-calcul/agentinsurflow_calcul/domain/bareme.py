"""Barème de risque déterministe : six règles évaluées dans l'ordre R01→R06."""

from __future__ import annotations

import operator
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from agentinsurflow_calcul.domain.models import (
    DonneeHorsBareme,
    FaitsRisque,
    RegleDeclenchee,
    ResultatRisque,
    verifier_crm,
)

VERSION_BAREME = "bareme-2026.10-v1"

DATE_BAREME = "2026-10-26"

Operateur = Literal[">=", ">", "<"]
_OPERATEURS: dict[str, Callable[[Decimal, Decimal], bool]] = {
    ">=": operator.ge,
    ">": operator.gt,
    "<": operator.lt,
}


@dataclass(frozen=True)
class Condition:
    """Un test ``champ <opérateur> seuil`` sur un fait du dossier."""

    champ: str
    operateur: Operateur
    seuil: Decimal


@dataclass(frozen=True)
class Regle:
    """Une règle du barème : déclenchée quand toutes ses conditions sont vraies."""

    regle_id: str
    libelle: str
    conditions: tuple[Condition, ...]
    motif: str
    effet: Literal["REFUSE"]


REGLES: tuple[Regle, ...] = (
    Regle(
        "R01_SUSPENSION",
        "Suspension de permis",
        (Condition("suspensions", ">=", Decimal(1)),),
        "Le relevé d'information mentionne une suspension de permis.",
        "REFUSE",
    ),
    Regle(
        "R02_RESILIATIONS",
        "Résiliations antérieures",
        (Condition("resiliations", ">=", Decimal(2)),),
        "Le relevé d'information mentionne au moins deux résiliations.",
        "REFUSE",
    ),
    Regle(
        "R03_CRM",
        "Coefficient bonus-malus élevé",
        (Condition("crm", ">", Decimal("1.25")),),
        "Le coefficient bonus-malus dépasse 1,25.",
        "REFUSE",
    ),
    Regle(
        "R04_SINISTRES_RESPONSABLES",
        "Sinistres responsables répétés",
        (Condition("nb_sinistres_responsables_trois_ans", ">", Decimal(2)),),
        "Plus de deux sinistres responsables dans les 36 mois avant la date d'effet.",
        "REFUSE",
    ),
    Regle(
        "R05_SINISTRES_TOTAL",
        "Fréquence de sinistres élevée",
        (Condition("nb_sinistres_trois_ans", ">", Decimal(4)),),
        "Plus de quatre sinistres dans les 36 mois avant la date d'effet.",
        "REFUSE",
    ),
    Regle(
        "R06_JEUNE_PERMIS_PUISSANCE",
        "Jeune permis et véhicule puissant",
        (
            Condition("anciennete_permis_mois", "<", Decimal(36)),
            Condition("puissance_fiscale_cv", ">", Decimal(7)),
        ),
        "Permis de moins de 3 ans et véhicule de plus de 7 CV.",
        "REFUSE",
    ),
)


def evaluer(faits: FaitsRisque) -> ResultatRisque:
    """Applique toutes les règles ; une seule suffit à refuser, le score les compte."""
    if faits.suspensions is None:
        raise DonneeHorsBareme("suspensions")
    if faits.resiliations is None:
        raise DonneeHorsBareme("resiliations")
    crm = verifier_crm(faits.crm)
    if faits.nb_sinistres_responsables_trois_ans is None:
        raise DonneeHorsBareme("nb_sinistres_responsables_trois_ans")
    if faits.nb_sinistres_trois_ans is None:
        raise DonneeHorsBareme("nb_sinistres_trois_ans")
    if faits.anciennete_permis_mois is None:
        raise DonneeHorsBareme("anciennete_permis_mois")
    if faits.puissance_fiscale_cv is None:
        raise DonneeHorsBareme("puissance_fiscale_cv")

    valeurs: dict[str, Decimal] = {
        "suspensions": Decimal(faits.suspensions),
        "resiliations": Decimal(faits.resiliations),
        "crm": crm,
        "nb_sinistres_responsables_trois_ans": Decimal(faits.nb_sinistres_responsables_trois_ans),
        "nb_sinistres_trois_ans": Decimal(faits.nb_sinistres_trois_ans),
        "anciennete_permis_mois": Decimal(faits.anciennete_permis_mois),
        "puissance_fiscale_cv": Decimal(faits.puissance_fiscale_cv),
    }
    declenchees = tuple(
        RegleDeclenchee(r.regle_id, r.motif)
        for r in REGLES
        if all(_OPERATEURS[c.operateur](valeurs[c.champ], c.seuil) for c in r.conditions)
    )
    refus = bool(declenchees)
    return ResultatRisque(
        version_bareme=VERSION_BAREME,
        classe="refus" if refus else "acceptable",
        decision="REFUSE" if refus else "ACCEPTE",
        score=float(len(declenchees)),
        regles=declenchees,
    )
