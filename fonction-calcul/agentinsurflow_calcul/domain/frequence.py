"""Prédiction de fréquence d'un GLM Poisson lu dans son artefact JSON (stdlib seule).

Seule implémentation de la prédiction : l'entraînement la compare à scikit-learn, la Function
la réutilise. Comparaison seulement : la fréquence n'entre ni dans la décision ni dans la prime.
"""

import math
from typing import Any


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
