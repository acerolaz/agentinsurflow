"""Unitaires — l'extraction big data freMTPL2 sur de minuscules ARFF écrits en ligne.

La CI n'installe pas le groupe ``bigdata`` : sans pyspark ni Java, tout le module est sauté.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

pytest.importorskip("pyspark")


def _java_present() -> bool:
    try:
        return subprocess.run(["java", "-version"], capture_output=True).returncode == 0
    except OSError:
        return False


if not _java_present():
    pytest.skip("Java 17 introuvable (brew install openjdk@17)", allow_module_level=True)

from pyspark.sql import SparkSession  # noqa: E402

from tools import extraction_bigdata as eb  # noqa: E402

ENTETE_FREQ = (
    "@relation freMTPL2freq\n@attribute IDpol numeric\n@attribute ClaimNb numeric\n"
    "@attribute Exposure numeric\n@attribute BonusMalus numeric\n"
    "@attribute Region {'R11','R82'}\n@data\n"
)
ENTETE_SEV = (
    "@relation freMTPL2sev\n@attribute IDpol numeric\n@attribute ClaimAmount numeric\n@data\n"
)


@pytest.fixture(scope="module")
def spark() -> Iterator[SparkSession]:
    session = eb.session_spark()
    yield session
    session.stop()


def _ecrire(chemin: Path, entete: str, lignes: list[str]) -> Path:
    chemin.write_text(entete + "\n".join(lignes) + "\n", encoding="utf-8")
    return chemin


def _parquets(
    spark: SparkSession, tmp_path: Path, freq: list[str], sev: list[str]
) -> tuple[Path, Path]:
    arff_f = _ecrire(tmp_path / "freq.arff", ENTETE_FREQ, freq)
    arff_s = _ecrire(tmp_path / "sev.arff", ENTETE_SEV, sev)
    eb.vers_parquet(spark, arff_f, tmp_path / "freq.parquet")
    eb.vers_parquet(spark, arff_s, tmp_path / "sev.parquet")
    return tmp_path / "freq.parquet", tmp_path / "sev.parquet"


def test_vers_parquet_lit_l_arff(spark: SparkSession, tmp_path: Path) -> None:
    arff = _ecrire(tmp_path / "sev.arff", ENTETE_SEV, ["1,100", "2,200", "3,300"])
    eb.vers_parquet(spark, arff, tmp_path / "sev.parquet")
    relu = spark.read.parquet(str(tmp_path / "sev.parquet"))
    assert relu.count() == 3
    assert relu.columns == ["IDpol", "ClaimAmount"]


def test_frequence_par_region_filtre_les_bornes(spark: SparkSession, tmp_path: Path) -> None:
    freq = [
        "1,1,0.5,60,'R11'",
        "2,0,1.0,100,'R11'",
        "3,0,0.0,100,'R11'",  # Exposure = 0 : exclu
        "4,0,0.5,300,'R11'",  # BonusMalus = 300 : exclu
    ]
    pf, ps = _parquets(spark, tmp_path, freq, ["1,100"])
    lignes = [r for r in eb.executer(spark, pf, ps) if r["requete"] == "frequence_par_region"]
    assert len(lignes) == 1
    assert lignes[0]["Region"] == "R11"
    assert lignes[0]["contrats"] == 2
    assert lignes[0]["frequence"] == pytest.approx(1 / 1.5)


def test_jointure_ignore_les_sinistres_sans_contrat(spark: SparkSession, tmp_path: Path) -> None:
    freq = ["1,1,1.0,60,'R11'", "2,2,1.0,120,'R82'"]
    sev = ["1,100", "2,200", "2,400", "99,9999"]  # 99 : aucun contrat
    pf, ps = _parquets(spark, tmp_path, freq, sev)
    lignes = {
        r["tranche_bm"]: r
        for r in eb.executer(spark, pf, ps)
        if r["requete"] == "cout_moyen_par_bonus_malus"
    }
    assert set(lignes) == {"50-99", "100-149"}
    assert lignes["50-99"]["cout_moyen"] == pytest.approx(100.0)
    assert lignes["100-149"]["cout_moyen"] == pytest.approx(300.0)
    assert lignes["100-149"]["contrats_sinistres"] == 1


def test_main_sans_java(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setattr(shutil, "which", lambda _nom: None)
    monkeypatch.delenv("JAVA_HOME", raising=False)
    assert eb.main(["--cache", str(tmp_path), "--sortie", str(tmp_path)]) == 1
    assert "Java 17 requis" in capsys.readouterr().err
