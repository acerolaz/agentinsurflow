"""Fusion des rapports d'agents dans l'état du dossier (D89) : propriété, type, unicité."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any, Literal

from agentinsurflow_cluster.domain.models import (
    EtatDossier,
    Fiche,
    NomAgent,
    Pieces,
    Prime,
    Rapport,
    Risque,
    Section,
)

PROPRIETAIRE: Mapping[Section, NomAgent | Literal["saga"]] = {
    "dossier": "saga",
    "pieces": "pieces",
    "risque": "analyste",
    "sources": "redacteur",
    "fiche": "redacteur",
    "prime": "actuaire",
    "validation": "saga",
    "pilotage": "saga",
}

_TYPES: Mapping[Section, type] = {
    "dossier": dict,
    "pieces": Pieces,
    "risque": Risque,
    "sources": tuple,
    "fiche": Fiche,
    "prime": Prime,
    "validation": dict,
}


class FusionRefusee(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def fusionner(etat: EtatDossier, rapport: Rapport) -> EtatDossier:
    """Fusionne le rapport ou lève `FusionRefusee(code)` ; l'état d'entrée n'est jamais modifié."""
    if not rapport.section:
        # Aucune référence exploitable : la cause envoie en revue humaine, sinon rapport vide.
        if rapport.cause is None:
            raise FusionRefusee("RAPPORT_VIDE")
        return replace(etat, cause=rapport.cause)
    for section, valeur in rapport.section.items():
        if PROPRIETAIRE.get(section) != rapport.agent:
            raise FusionRefusee("SECTION_NON_POSSEDEE")
        # Un type absent de _TYPES (pilotage) est invalide : la Saga seule le porte.
        if not isinstance(valeur, _TYPES.get(section, type(None))):
            raise FusionRefusee("TYPE_INVALIDE")
        # `pieces` est réécrivable une fois par tentative (D89).
        reecriture_permise = (
            section == "pieces"
            and etat.pieces_tentative is not None
            and etat.pieces_tentative < etat.tentative
        )
        if getattr(etat, section) is not None and not reecriture_permise:
            raise FusionRefusee("DEJA_REMPLIE")
    champs: dict[str, Any] = {k: v for k, v in rapport.section.items()}
    if "pieces" in champs:
        champs["pieces_tentative"] = etat.tentative
    return replace(etat, **champs)
