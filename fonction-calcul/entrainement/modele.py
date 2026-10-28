# ruff: noqa: E501
"""GLM Poisson de fréquence : entraînement, évaluation, artefact JSON, fiche, porte (C12).

`PoissonRegressor` sur `y = ClaimNb / Exposure` avec `sample_weight = Exposure` est équivalent
exact du GLM log-Poisson avec offset `log(Exposure)`.
Rôle : comparaison seulement, la fréquence n'entre jamais dans la décision ni dans la prime.
"""

from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import PoissonRegressor
from sklearn.metrics import mean_poisson_deviance

from entrainement import donnees

ALPHA = 1e-4
MAX_ITER = 1000
VEH_POWERS = list(range(donnees.VEH_POWER_MIN, donnees.VEH_POWER_MAX + 1))
# Modalités de référence (coefficient 0.0 explicite dans l'artefact).
REF_VEH_POWER = VEH_POWERS[0]
REF_REGION = donnees.REGIONS[0]
DECILES = 10
CHIFFRES = 12


def _arrondi(x: float) -> float:
    return float(f"{x:.{CHIFFRES}g}")


def matrice(df: pd.DataFrame) -> np.ndarray:
    """log(BonusMalus), puis indicatrices VehPower et Region (hors modalités de référence)."""
    cols = [np.log(df["BonusMalus"].to_numpy(dtype=float))]
    cols += [(df["VehPower"] == v).to_numpy(dtype=float) for v in VEH_POWERS[1:]]
    cols += [(df["Region"] == r).to_numpy(dtype=float) for r in donnees.REGIONS[1:]]
    return np.column_stack(cols)


def entrainer(train: pd.DataFrame) -> PoissonRegressor:
    m = PoissonRegressor(alpha=ALPHA, max_iter=MAX_ITER, tol=1e-10)
    m.fit(
        matrice(train),
        train["ClaimNb"] / train["Exposure"],
        sample_weight=train["Exposure"],
    )
    return m


def _deviance(df: pd.DataFrame, mu: np.ndarray | float) -> float:
    y = (df["ClaimNb"] / df["Exposure"]).to_numpy()
    mu = np.broadcast_to(np.asarray(mu, dtype=float), y.shape)
    return float(mean_poisson_deviance(y, mu, sample_weight=df["Exposure"].to_numpy()))


def _gini(mu: np.ndarray, sinistres: np.ndarray, expo: np.ndarray) -> float:
    """1 - 2·aire sous la courbe de Lorenz (sinistres cumulés / exposition cumulée, mu croissante).

    Les ex æquo de `mu` sont regroupés : le résultat ne dépend pas de l'ordre des lignes.
    """
    valeurs, inverse = np.unique(mu, return_inverse=True)
    expo_g = np.bincount(inverse, weights=expo, minlength=len(valeurs))
    sin_g = np.bincount(inverse, weights=sinistres, minlength=len(valeurs))
    x = np.concatenate([[0.0], np.cumsum(expo_g) / expo_g.sum()])
    y = np.concatenate([[0.0], np.cumsum(sin_g) / sin_g.sum()])
    return float(1 - 2 * np.sum((x[1:] - x[:-1]) * (y[1:] + y[:-1]) / 2))


def _calibration(mu: np.ndarray, sinistres: np.ndarray, expo: np.ndarray) -> list[dict[str, Any]]:
    """10 groupes d'égale exposition, triés par fréquence prédite croissante."""
    ordre = np.argsort(mu, kind="stable")
    mu, sinistres, expo = mu[ordre], sinistres[ordre], expo[ordre]
    milieu = (np.cumsum(expo) - expo / 2) / expo.sum()
    groupe = np.minimum((milieu * DECILES).astype(int), DECILES - 1)
    out = []
    for d in range(DECILES):
        m = groupe == d
        w = expo[m].sum()
        out.append(
            {
                "decile": d + 1,
                "predite": _arrondi(float((mu[m] * expo[m]).sum() / w)),
                "observee": _arrondi(float(sinistres[m].sum() / w)),
            }
        )
    return out


def evaluer(m: PoissonRegressor, test: pd.DataFrame, train: pd.DataFrame) -> dict[str, Any]:
    """Métriques sur le test ; le modèle nul est la fréquence moyenne pondérée de l'entraînement."""
    mu = m.predict(matrice(test))
    nul = float(train["ClaimNb"].sum() / train["Exposure"].sum())
    dev, dev_nul = _deviance(test, mu), _deviance(test, nul)
    sinistres = test["ClaimNb"].to_numpy(dtype=float)
    expo = test["Exposure"].to_numpy(dtype=float)
    return {
        "deviance_moyenne": _arrondi(dev),
        "deviance_moyenne_nul": _arrondi(dev_nul),
        "d2": _arrondi(1 - dev / dev_nul),
        "gini": _arrondi(_gini(mu, sinistres, expo)),
        "calibration": _calibration(mu, sinistres, expo),
        "lignes_train": len(train),
        "lignes_test": len(test),
    }


def exporter(
    m: PoissonRegressor,
    metriques: dict[str, Any],
    source: dict[str, Any],
    version: str,
    *,
    commit: str,
    entraine_le: str,
) -> dict[str, Any]:
    """Artefact JSON : lisible, sans pickle ; indicatrices de référence à 0.0 explicite."""
    coef = [float(c) for c in m.coef_]
    n_vp = len(VEH_POWERS) - 1
    vp = {str(REF_VEH_POWER): 0.0} | {
        str(v): _arrondi(c) for v, c in zip(VEH_POWERS[1:], coef[1 : 1 + n_vp], strict=True)
    }
    reg = {REF_REGION: 0.0} | {
        r: _arrondi(c) for r, c in zip(donnees.REGIONS[1:], coef[1 + n_vp :], strict=True)
    }
    return {
        "version": version,
        "intercept": _arrondi(float(m.intercept_)),
        "alpha": m.alpha,
        "bonus_malus": {
            "min": donnees.BONUS_MALUS_MIN,
            "max": donnees.BONUS_MALUS_MAX,
            "coef": _arrondi(coef[0]),
        },
        "veh_power": {"min": donnees.VEH_POWER_MIN, "max": donnees.VEH_POWER_MAX, "coefs": vp},
        "region": {"coefs": reg},
        "donnees": source,
        "metriques": metriques,
        "commit": commit,
        "entraine_le": entraine_le,
    }


def porte(metriques: dict[str, Any], seuils: dict[str, Any]) -> list[str]:
    """Raisons d'échec de la porte de qualité (liste vide si elle passe)."""
    raisons = []
    if metriques["deviance_moyenne"] >= metriques["deviance_moyenne_nul"]:
        raisons.append("le modèle ne bat pas le modèle nul (déviance >= déviance du nul)")
    if metriques["d2"] < seuils["d2_min"]:
        raisons.append(f"D² {metriques['d2']:.6f} < seuil {seuils['d2_min']:.6f}")
    return raisons


def fiche(artefact: dict[str, Any], seuils: dict[str, Any] | None = None) -> str:
    """Fiche du modèle (Markdown), générée des mêmes données que l'artefact."""
    m, d = artefact["metriques"], artefact["donnees"]
    bm, vp = artefact["bonus_malus"], artefact["veh_power"]
    cal = "\n".join(
        f"| {c['decile']} | {c['predite']:.4f} | {c['observee']:.4f} |" for c in m["calibration"]
    )
    seuil = (
        f"D² du test >= **{seuils['d2_min']:.6f}** (mesure {seuils['d2_mesure']:.6f} du "
        f"{seuils['mesure_le']}, moins une marge de 0,005) ; le modèle doit aussi battre le modèle nul."
        if seuils
        else "non encore fixé."
    )
    return f"""# Fiche du modèle {artefact["version"]}

GLM de Poisson de **fréquence annuelle de sinistres** (compétence C12). **Comparaison seulement** :
la fréquence n'entre jamais dans la décision, la prime ni le rapport de l'Actuaire.

## Données
- Source : {d["nom"]} (OpenML {d["openml_data_id"]}, version {d["version"]}), {d["url"]}
- Origine : {d["origine"]}
- Licence : **{d["licence"]}**
- SHA-256 du fichier : `{d["sha256"]}`
- Jamais commité ; aucune donnée personnelle réelle. Partage 80 / 20 (graine 42) :
  {m["lignes_train"]} lignes d'entraînement, {m["lignes_test"]} de test.

## Variables
- **Utilisées** : `BonusMalus` (= `crm` × 100, en `log`, borné à [{bm["min"]}, {bm["max"]}]),
  `VehPower` (= `puissance_fiscale_cv`, bornée à [{vp["min"]}, {vp["max"]}], modalités >= 12 regroupées,
  indicatrices, référence {REF_VEH_POWER}), `Region` (département → ancienne région,
  22 indicatrices, référence {REF_REGION}).
- **Exclues** : `DrivAge`, `VehAge`, `VehBrand`, `VehGas`, `Area`, `Density`. Elles n'ont pas
  d'équivalent dans un dossier AgentInsurFlow (par exemple, `anciennete_permis_mois` n'est pas
  un âge) : limite assumée, l'objet est la chaîne C12/C13, pas la précision du produit.

## Exposition
`PoissonRegressor` sur `y = ClaimNb / Exposure` avec `sample_weight = Exposure` est **équivalent
exact** du GLM log-Poisson avec offset `log(Exposure)`. `Exposure` est plafonnée à 1, `ClaimNb` à 4.

## Hyperparamètre
`alpha` = {artefact["alpha"]} (régularisation L2 faible, fixée d'avance, non ajustée sur le test).

## Métriques (jeu de test)
| Mesure | Modèle | Modèle nul |
|---|---|---|
| Déviance de Poisson moyenne (pondérée par l'exposition) | {m["deviance_moyenne"]:.6f} | {m["deviance_moyenne_nul"]:.6f} |

- D² = 1 − déviance / déviance du nul : **{m["d2"]:.6f}**
- Gini (courbe de Lorenz pondérée par l'exposition) : **{m["gini"]:.6f}**

### Calibration (10 déciles de fréquence prédite, d'égale exposition)
| Décile | Prédite | Observée |
|---|---|---|
{cal}

## Seuil de la porte de qualité
{seuil}

## Traçabilité
Version `{artefact["version"]}`, entraîné le {artefact["entraine_le"]}, commit `{artefact["commit"]}`.

## Limites
Trois variables seulement ; jeu français historique (freMTPL2) ; entrées hors bornes **bornées**,
jamais extrapolées ; départements d'outre-mer hors modèle. Usage : comparaison avec le barème,
jamais décision ni tarification.
"""
