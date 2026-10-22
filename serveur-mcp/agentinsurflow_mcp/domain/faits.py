"""Faits envoyés à la Function de calcul, tirés de la vue du contrat (``VueContrat``).

Une donnée absente ou ``None`` reste ``None`` : la Function répond ``DONNEE_HORS_BAREME``.
"""

from __future__ import annotations

from typing import Any


def _crm(contrat: dict[str, Any]) -> str | None:
    valeur = contrat.get("crm_bonus_malus")
    return None if valeur is None else str(valeur)  # décimal en texte : pas de flottant en JSON


def faits_risque(contrat: dict[str, Any]) -> dict[str, Any]:
    cles = (
        "suspensions",
        "resiliations",
        "nb_sinistres_responsables_trois_ans",
        "nb_sinistres_trois_ans",
        "anciennete_permis_mois",
        "puissance_fiscale_cv",
    )
    return {cle: contrat.get(cle) for cle in cles} | {"crm": _crm(contrat)}


def faits_prime(contrat: dict[str, Any]) -> dict[str, Any]:
    cles = (
        "formule",
        "anciennete_permis_mois",
        "departement",
        "puissance_fiscale_cv",
        "type_usage",
    )
    return {cle: contrat.get(cle) for cle in cles} | {"crm": _crm(contrat)}
