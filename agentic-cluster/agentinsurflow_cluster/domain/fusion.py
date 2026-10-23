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

PROPRIETAIRE: Mapping[Section, NomAgent | Literal["orchestrateur"]] = {
    "dossier": "orchestrateur",
    "pieces": "pieces",
    "risque": "analyste",
    "sources": "redacteur",
    "fiche": "redacteur",
    "prime": "actuaire",
    "validation": "orchestrateur",
    "pilotage": "orchestrateur",
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
    for section, valeur in rapport.section.items():
        if PROPRIETAIRE.get(section) != rapport.agent:
            raise FusionRefusee("SECTION_NON_POSSEDEE")
        # Un type absent de _TYPES (pilotage) est invalide : l'orchestrateur seul le porte.
        if not isinstance(valeur, _TYPES.get(section, type(None))):
            raise FusionRefusee("TYPE_INVALIDE")
        # `pieces` est réécrivable à partir de la 2e tentative (D89) ; ailleurs, une fois seulement.
        reecriture_permise = section == "pieces" and etat.tentative > 1
        if getattr(etat, section) is not None and not reecriture_permise:
            raise FusionRefusee("DEJA_REMPLIE")
    champs: dict[str, Any] = {k: v for k, v in rapport.section.items()}
    nouveau = replace(etat, **champs)
    # Rédacteur en repli sans fiche : la cause envoie le dossier en revue humaine.
    if rapport.agent == "redacteur" and rapport.cause and "fiche" not in rapport.section:
        nouveau = replace(nouveau, cause=rapport.cause)
    return nouveau
