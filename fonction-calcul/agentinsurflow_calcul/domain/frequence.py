"""Prédiction de fréquence d'un GLM Poisson lu dans son artefact JSON (stdlib seule).

Seule implémentation de la prédiction : l'entraînement la compare à scikit-learn, la Function
la réutilise. Comparaison seulement : la fréquence n'entre ni dans la décision ni dans la prime.
"""

import json
import math
from dataclasses import dataclass
from decimal import Decimal
from functools import cache
from importlib import resources
from typing import Any

from agentinsurflow_calcul.domain.regions import REGION_PAR_DEPARTEMENT


def predire_depuis_artefact(
    artefact: dict[str, Any], bonus_malus: float, veh_power: int, region: str
) -> float:
    """Fréquence annuelle `exp(intercept + coef·log(BM) + VehPower + Region)`, bornes de l'artefact.

    Les entrées hors des bornes d'entraînement sont bornées, jamais extrapolées.
    `region` inconnue : KeyError (à traduire par l'appelant).
    """
    bm = artefact["bonus_malus"]
    vp = artefact["veh_power"]
    bonus = min(max(bonus_malus, bm["min"]), bm["max"])
    puissance = min(max(veh_power, vp["min"]), vp["max"])
    lineaire = (
        artefact["intercept"]
        + bm["coef"] * math.log(bonus)
        + vp["coefs"][str(puissance)]
        + artefact["region"]["coefs"][region]
    )
    return math.exp(lineaire)


class DonneeHorsModele(Exception):
    """Un champ manque ou n'a pas d'équivalent dans le modèle (ex. DOM) : pas de prédiction."""

    def __init__(self, champ: str) -> None:
        super().__init__(champ)
        self.champ = champ  # le nom du champ, jamais sa valeur


@dataclass(frozen=True)
class ProfilFrequence:
    crm: Decimal | None
    puissance_fiscale_cv: int | None
    departement: str | None


@dataclass(frozen=True)
class PredictionFrequence:
    version_modele: str
    frequence_annuelle: float


@cache
def charger_modele() -> dict[str, Any]:
    """Artefact le plus récent par nom dans `modeles/`, lu une seule fois."""
    dossier = resources.files("agentinsurflow_calcul") / "modeles"
    dernier = max((f for f in dossier.iterdir() if f.name.endswith(".json")), key=lambda f: f.name)
    artefact: dict[str, Any] = json.loads(dernier.read_text(encoding="utf-8"))
    return artefact


def predire(artefact: dict[str, Any], profil: ProfilFrequence) -> PredictionFrequence:
    """Fréquence annuelle du profil ; `DonneeHorsModele(champ)` si champ absent ou sans région."""
    if profil.crm is None:
        raise DonneeHorsModele("crm")
    if profil.puissance_fiscale_cv is None:
        raise DonneeHorsModele("puissance_fiscale_cv")
    region = REGION_PAR_DEPARTEMENT.get(profil.departement or "")
    if region is None:
        raise DonneeHorsModele("departement")
    frequence = predire_depuis_artefact(
        artefact, float(profil.crm) * 100, profil.puissance_fiscale_cv, region
    )
    return PredictionFrequence(artefact["version"], frequence)
