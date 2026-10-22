"""Barème de risque déterministe : six règles évaluées dans l'ordre R01→R06."""

from __future__ import annotations

from decimal import Decimal

from agentinsurflow_calcul.domain.models import (
    DonneeHorsBareme,
    FaitsRisque,
    RegleDeclenchee,
    ResultatRisque,
    verifier_crm,
)

VERSION_BAREME = "bareme-2026.10-v1"

_SEUIL_CRM = Decimal("1.25")


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

    regles = [
        (
            faits.suspensions >= 1,
            "R01_SUSPENSION",
            "Le relevé d'information mentionne une suspension de permis.",
        ),
        (
            faits.resiliations >= 2,
            "R02_RESILIATIONS",
            "Le relevé d'information mentionne au moins deux résiliations.",
        ),
        (crm > _SEUIL_CRM, "R03_CRM", "Le coefficient bonus-malus dépasse 1,25."),
        (
            faits.nb_sinistres_responsables_trois_ans > 2,
            "R04_SINISTRES_RESPONSABLES",
            "Plus de deux sinistres responsables dans les 36 mois avant la date d'effet.",
        ),
        (
            faits.nb_sinistres_trois_ans > 4,
            "R05_SINISTRES_TOTAL",
            "Plus de quatre sinistres dans les 36 mois avant la date d'effet.",
        ),
        (
            faits.anciennete_permis_mois < 36 and faits.puissance_fiscale_cv > 7,
            "R06_JEUNE_PERMIS_PUISSANCE",
            "Permis de moins de 3 ans et véhicule de plus de 7 CV.",
        ),
    ]
    declenchees = tuple(RegleDeclenchee(i, m) for ok, i, m in regles if ok)
    refus = bool(declenchees)
    return ResultatRisque(
        version_bareme=VERSION_BAREME,
        classe="refus" if refus else "acceptable",
        decision="REFUSE" if refus else "ACCEPTE",
        score=float(len(declenchees)),
        regles=declenchees,
    )
