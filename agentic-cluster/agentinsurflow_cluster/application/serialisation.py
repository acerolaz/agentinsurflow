"""Sérialisation JSON-safe de l'état du dossier (point de reprise et corps d'``enregistrer_etat``).

Un point de reprise LangGraph transforme les tuples en listes : ``etat_depuis_dict`` les rétablit,
sans quoi la fusion (``isinstance(..., tuple)``) refuserait l'état relu.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from typing import Any

from agentinsurflow_cluster.domain.models import EtatDossier, Fiche, Pieces, Prime, Risque

_SECTIONS: dict[str, type] = {"pieces": Pieces, "risque": Risque, "fiche": Fiche, "prime": Prime}


def vers_json(valeur: Any) -> Any:
    """Dataclasses, dicts, tuples et listes en structures JSON (tuples ⇒ listes)."""
    if is_dataclass(valeur) and not isinstance(valeur, type):
        return {f.name: vers_json(getattr(valeur, f.name)) for f in fields(valeur)}
    if isinstance(valeur, dict):
        return {k: vers_json(v) for k, v in valeur.items()}
    if isinstance(valeur, tuple | list):
        return [vers_json(v) for v in valeur]
    return valeur


def _construire(cls: type, brut: dict[str, Any]) -> Any:
    return cls(
        **{
            f.name: tuple(brut[f.name])
            if isinstance(brut[f.name], list) and "tuple" in str(f.type)
            else brut[f.name]
            for f in fields(cls)
        }
    )


def etat_vers_dict(etat: EtatDossier) -> dict[str, Any]:
    return vers_json(etat)  # type: ignore[no-any-return]


def etat_depuis_dict(brut: dict[str, Any]) -> EtatDossier:
    sections = {
        nom: None if brut[nom] is None else _construire(cls, brut[nom])
        for nom, cls in _SECTIONS.items()
    }
    return _construire(EtatDossier, {**brut, **sections})  # type: ignore[no-any-return]
