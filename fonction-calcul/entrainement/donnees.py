"""Données freMTPL2 : téléchargement figé, préparation, partage entraînement / test (C12).

Les bornes de préparation sont fixes (décidées, pas apprises) : le jeu de test n'influence
jamais la préparation.
"""

import hashlib
import tomllib
import urllib.request
from pathlib import Path
from typing import Any

import pandas as pd
from sklearn.model_selection import train_test_split

_TOML = tomllib.loads((Path(__file__).parent / "donnees.toml").read_text("utf-8"))
_SOURCE: dict[str, Any] = _TOML["source"]
SOURCE_SEV: dict[str, Any] = _TOML["source_sev"]
URL: str = _SOURCE["url"]
NOM_FICHIER: str = _SOURCE["fichier"]
SHA256: str = _SOURCE["sha256"]
LIGNES: int = _SOURCE["lignes"]

COLONNES = ["ClaimNb", "Exposure", "BonusMalus", "VehPower", "Region"]
REGIONS = [
    "R11", "R21", "R22", "R23", "R24", "R25", "R26", "R31", "R41", "R42", "R43",
    "R52", "R53", "R54", "R72", "R73", "R74", "R82", "R83", "R91", "R93", "R94",
]  # fmt: skip
EXPOSURE_MAX = 1.0
CLAIM_NB_MAX = 4
BONUS_MALUS_MIN, BONUS_MALUS_MAX = 50, 230
VEH_POWER_MIN, VEH_POWER_MAX = 4, 12  # modalités >= 12 regroupées en 12


def _sha256(fichier: Path) -> str:
    return hashlib.sha256(fichier.read_bytes()).hexdigest()


def telecharger(cache: Path, source: dict[str, Any] = _SOURCE) -> Path:
    """Fichier de `source` dans `cache` (téléchargé s'il manque), SHA-256 toujours vérifié."""
    fichier: Path = cache / source["fichier"]
    if not fichier.exists():
        with urllib.request.urlopen(source["url"], timeout=120) as reponse:
            fichier.write_bytes(reponse.read())
    if _sha256(fichier) != source["sha256"]:
        raise ValueError(f"SHA-256 de {fichier.name} différent de celui figé dans donnees.toml")
    return fichier


def attributs(fichier: Path) -> list[str]:
    """Noms des lignes `@attribute` de l'en-tête ARFF, jusqu'à `@data`."""
    noms: list[str] = []
    with fichier.open(encoding="utf-8") as f:
        for ligne in f:
            if ligne.lower().startswith("@attribute"):
                noms.append(ligne.split()[1])
            elif ligne.lower().startswith("@data"):
                break
    return noms


def charger(fichier: Path) -> pd.DataFrame:
    """Lit l'ARFF avec pandas seul (en-tête `@attribute`, puis CSV) : colonnes utiles."""
    noms = attributs(fichier)
    with fichier.open(encoding="utf-8") as f:
        for ligne in f:
            if ligne.lower().startswith("@data"):
                break
        df = pd.read_csv(f, names=noms, quotechar="'", usecols=COLONNES)
    return df[COLONNES]


def preparer(df: pd.DataFrame) -> pd.DataFrame:
    """Bornes fixes : Exposure <= 1, ClaimNb <= 4, BonusMalus [50, 230], VehPower [4, 12]."""
    inconnues = set(df["Region"]) - set(REGIONS)
    if inconnues:
        raise ValueError(f"Region hors des 22 régions de freMTPL2 : {sorted(inconnues)}")
    out = df[df["Exposure"] > 0][COLONNES].copy()
    out["Exposure"] = out["Exposure"].clip(upper=EXPOSURE_MAX)
    out["ClaimNb"] = out["ClaimNb"].clip(upper=CLAIM_NB_MAX)
    out["BonusMalus"] = out["BonusMalus"].clip(BONUS_MALUS_MIN, BONUS_MALUS_MAX)
    out["VehPower"] = out["VehPower"].clip(VEH_POWER_MIN, VEH_POWER_MAX)
    return out


def separer(
    df: pd.DataFrame, graine: int = 42, part_test: float = 0.2
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Partage entraînement / test sur l'index, déterministe."""
    idx_train, idx_test = train_test_split(df.index, test_size=part_test, random_state=graine)
    return df.loc[idx_train], df.loc[idx_test]
