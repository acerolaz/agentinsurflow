"""GLM Poisson de fréquence (C12) : entraînement, évaluation, artefact, porte.

Niveau : TU (données synthétiques à effet de BonusMalus connu, aucune I/O).
"""

import json
import warnings

import numpy as np
import pandas as pd
import pytest
from entrainement import donnees, modele
from sklearn.exceptions import ConvergenceWarning

from agentinsurflow_calcul.domain.frequence import predire_depuis_artefact

EFFET_BM = 1.2  # coefficient vrai de log(BonusMalus)
SOURCE = {"nom": "synthetique"}


def _synthetique(n: int = 20_000, graine: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(graine)
    df = pd.DataFrame(
        {
            "BonusMalus": rng.integers(50, 231, n),
            "VehPower": rng.integers(4, 13, n),
            "Region": rng.choice(donnees.REGIONS, n),
            "Exposure": rng.uniform(0.1, 1.0, n),
        }
    )
    mu = np.exp(-4.0 + EFFET_BM * np.log(df["BonusMalus"] / 100) + 0.05 * (df["VehPower"] - 4))
    df["ClaimNb"] = rng.poisson(mu * df["Exposure"]).clip(max=4)
    return df[donnees.COLONNES]


@pytest.fixture(scope="module")
def jeu() -> tuple[pd.DataFrame, pd.DataFrame, object]:
    train, test = donnees.separer(_synthetique())
    return train, test, modele.entrainer(train)


def _artefact(jeu, **kw) -> dict:
    train, test, m = jeu
    return modele.exporter(
        m,
        modele.evaluer(m, test, train),
        SOURCE,
        "glm-freq-test-v1",
        commit="abc",
        entraine_le="2026-10-28",
    )


def test_bat_le_modele_nul(jeu) -> None:
    train, test, m = jeu
    met = modele.evaluer(m, test, train)
    assert met["deviance_moyenne"] < met["deviance_moyenne_nul"]
    assert met["d2"] > 0 and met["gini"] > 0
    assert m.coef_[0] == pytest.approx(EFFET_BM, abs=0.1)  # l'effet connu est retrouvé


def test_entrainement_deterministe() -> None:
    def un() -> str:
        train, test = donnees.separer(_synthetique())
        m = modele.entrainer(train)
        art = modele.exporter(
            m, modele.evaluer(m, test, train), SOURCE, "v", commit="abc", entraine_le="2026-10-28"
        )
        return json.dumps(art, sort_keys=True, ensure_ascii=False)

    assert un() == un()


def test_converge() -> None:
    train, _ = donnees.separer(_synthetique())
    with warnings.catch_warnings():
        warnings.simplefilter("error", ConvergenceWarning)
        m = modele.entrainer(train)
    assert m.n_iter_ < m.max_iter


def test_artefact_predit_comme_sklearn(jeu) -> None:
    _, test, m = jeu
    lignes = test.head(1000)
    art = json.loads(json.dumps(_artefact(jeu)))  # relu comme le fera la Function
    attendu = m.predict(modele.matrice(lignes))
    obtenu = [
        predire_depuis_artefact(art, r.BonusMalus, r.VehPower, r.Region)
        for r in lignes.itertuples()
    ]
    assert np.max(np.abs(np.array(obtenu) - attendu)) <= 1e-9


def test_artefact_modalites_de_reference_et_bornes(jeu) -> None:
    art = _artefact(jeu)
    assert art["veh_power"]["coefs"]["4"] == 0.0 and art["region"]["coefs"]["R11"] == 0.0
    assert len(art["veh_power"]["coefs"]) == 9 and len(art["region"]["coefs"]) == 22
    # hors bornes : borné, pas extrapolé
    assert predire_depuis_artefact(art, 350, 40, "R11") == predire_depuis_artefact(
        art, 230, 12, "R11"
    )
    assert predire_depuis_artefact(art, 10, 2, "R11") == predire_depuis_artefact(art, 50, 4, "R11")


def test_porte_refuse_sous_le_seuil(jeu) -> None:
    train, test, m = jeu
    met = modele.evaluer(m, test, train)
    assert modele.porte(met, {"d2_min": met["d2"] - 0.005}) == []
    assert modele.porte(met, {"d2_min": met["d2"] + 0.01})
    assert modele.porte(dict(met, deviance_moyenne=met["deviance_moyenne_nul"]), {"d2_min": -1})


def test_calibration_dix_deciles(jeu) -> None:
    train, test, m = jeu
    cal = modele.evaluer(m, test, train)["calibration"]
    assert [c["decile"] for c in cal] == list(range(1, 11))
    predites = [c["predite"] for c in cal]
    assert predites == sorted(predites)
    assert all(c["observee"] >= 0 for c in cal)


def test_fiche_contient_les_rubriques(jeu) -> None:
    art = _artefact(jeu)
    art["donnees"] = {
        "nom": "n", "openml_data_id": 1, "version": "1", "url": "u", "origine": "o",
        "licence": "CC0", "sha256": "abc",
    }  # fmt: skip
    texte = modele.fiche(art, {"d2_min": 0.01, "d2_mesure": 0.015, "mesure_le": "2026-10-28"})
    for mot in ("CC0", "abc", "DrivAge", "offset", "alpha", "modèle nul", "Gini", "Limites"):
        assert mot in texte
