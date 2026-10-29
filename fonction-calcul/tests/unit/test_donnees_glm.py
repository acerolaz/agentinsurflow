"""Données freMTPL2 du GLM Poisson (C12) : préparation, partage, somme de contrôle.

Niveau : TU (DataFrame synthétique, fichiers temporaires, aucun réseau) ; le test `lent`
lit le vrai jeu (TI, cache local ou téléchargement).
"""

import os
from pathlib import Path

import pandas as pd
import pytest
from entrainement import donnees

REGIONS = donnees.REGIONS


def _brut(n: int = 100) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ClaimNb": [0, 1, 2, 9] * (n // 4),
            "Exposure": [0.05, 0.5, 1.0, 2.5] * (n // 4),
            "BonusMalus": [30, 50, 100, 350] * (n // 4),
            "VehPower": [2, 4, 9, 15] * (n // 4),
            "Region": ["R11", "R94", "R53", "R82"] * (n // 4),
        }
    )


def test_schema_et_bornes_apres_preparation() -> None:
    df = donnees.preparer(_brut())
    assert list(df.columns) == ["ClaimNb", "Exposure", "BonusMalus", "VehPower", "Region"]
    assert df["Exposure"].between(0, 1).all() and (df["Exposure"] > 0).all()
    assert df["ClaimNb"].between(0, 4).all()
    assert df["BonusMalus"].between(50, 230).all()
    assert df["VehPower"].between(4, 12).all()
    assert len(REGIONS) == 22 and set(df["Region"]) <= set(REGIONS)


def test_region_inconnue_refusee() -> None:
    brut = _brut()
    brut.loc[0, "Region"] = "R99"
    with pytest.raises(ValueError, match="Region"):
        donnees.preparer(brut)


def test_separation_sans_fuite() -> None:
    df = donnees.preparer(_brut(200))
    train, test = donnees.separer(df)
    assert set(train.index).isdisjoint(test.index)
    assert set(train.index) | set(test.index) == set(df.index)
    assert abs(len(test) - 0.2 * len(df)) <= 1


def test_separation_deterministe() -> None:
    df = donnees.preparer(_brut(200))
    a = donnees.separer(df)
    b = donnees.separer(df)
    assert list(a[1].index) == list(b[1].index)
    assert list(a[1].index) != list(donnees.separer(df, graine=7)[1].index)


def test_sha_incorrect_refuse(tmp_path: Path) -> None:
    (tmp_path / donnees.NOM_FICHIER).write_text("altéré")
    with pytest.raises(ValueError, match="SHA-256"):
        donnees.telecharger(tmp_path)


@pytest.mark.lent
def test_fremtpl2_reel_schema() -> None:
    cache = Path(os.environ.get("FREMTPL2_CACHE", "/tmp/fremtpl2-cache"))
    cache.mkdir(parents=True, exist_ok=True)
    df = donnees.charger(donnees.telecharger(cache))
    assert len(df) == donnees.LIGNES == 678_013
    assert list(df.columns) == ["ClaimNb", "Exposure", "BonusMalus", "VehPower", "Region"]
    assert set(df["Region"]) == set(REGIONS)
    assert len(donnees.preparer(df)) == len(df)


def test_charger_arff_minimal(tmp_path: Path) -> None:
    fichier = tmp_path / "mini.arff"
    fichier.write_text(
        "@relation m\n@attribute IDpol numeric\n@attribute ClaimNb numeric\n"
        "@attribute Exposure numeric\n@attribute VehPower numeric\n@attribute BonusMalus numeric\n"
        "@attribute VehGas string\n@attribute Region {'R11','R94'}\n@data\n"
        "1,1,0.5,5,50,'Diesel','R94'\n2,0,1.0,7,60,'Regular','R11'\n"
    )
    df = donnees.charger(fichier)
    assert list(df.columns) == ["ClaimNb", "Exposure", "BonusMalus", "VehPower", "Region"]
    assert list(df["Region"]) == ["R94", "R11"]


def test_source_sev_figee() -> None:
    assert donnees.SOURCE_SEV["sha256"] == (
        "047632016b87e132247124f449a95d6d0e9f8ba05f2fe0947ef76ab8aaa10e0a"
    )
    assert donnees.SOURCE_SEV["openml_data_id"] == 41215
    assert donnees.SOURCE_SEV["licence"] == "CC0"


def test_attributs_arff(tmp_path: Path) -> None:
    arff = tmp_path / "x.arff"
    arff.write_text(
        "@relation x\n@attribute IDpol numeric\n@attribute ClaimAmount numeric\n@data\n1,2.5\n",
        encoding="utf-8",
    )
    assert donnees.attributs(arff) == ["IDpol", "ClaimAmount"]
