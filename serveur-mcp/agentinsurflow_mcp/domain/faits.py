"""Faits envoyés à la Function de calcul, tirés de la vue du contrat (``VueContrat``).

Une donnée absente ou ``None`` reste ``None`` : la Function répond ``DONNEE_HORS_BAREME``.
Sans relevé d'information (``releve_present`` différent de ``True``, clé absente comprise),
les faits issus du relevé (``suspensions``, ``resiliations``, ``crm``, sinistres sur trois ans)
valent ``None`` : un dossier sans relevé n'est jamais accepté (la vue le remplace sinon par
des valeurs neutres).
"""

from __future__ import annotations

from typing import Any

_FAITS_DU_RELEVE = (
    "suspensions",
    "resiliations",
    "nb_sinistres_trois_ans",
    "nb_sinistres_responsables_trois_ans",
)


def _releve_present(contrat: dict[str, Any]) -> bool:
    return contrat.get("releve_present") is True


def _crm(contrat: dict[str, Any]) -> str | None:
    valeur = contrat.get("crm_bonus_malus")
    if valeur is None or not _releve_present(contrat):
        return None
    return str(valeur)  # décimal en texte : pas de flottant en JSON


def faits_risque(contrat: dict[str, Any]) -> dict[str, Any]:
    cles = (*_FAITS_DU_RELEVE, "anciennete_permis_mois", "puissance_fiscale_cv")
    faits = {cle: contrat.get(cle) for cle in cles}
    if not _releve_present(contrat):
        faits |= dict.fromkeys(_FAITS_DU_RELEVE)
    return faits | {"crm": _crm(contrat)}


def faits_prime(contrat: dict[str, Any]) -> dict[str, Any]:
    cles = (
        "formule",
        "anciennete_permis_mois",
        "departement",
        "puissance_fiscale_cv",
        "type_usage",
    )
    return {cle: contrat.get(cle) for cle in cles} | {"crm": _crm(contrat)}
