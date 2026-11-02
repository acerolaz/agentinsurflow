"""Unitaires — la porte de la pyramide de tests (70 / 20 / 10, S3-22), sans lancer de tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tools import pyramide
from tools.pyramide import NIVEAUX, compter, verifier


def test_verifier_accepte_70_20_10() -> None:
    assert verifier({"TU": 70, "TI": 20, "E2E": 10}) == []


def test_verifier_refuse_tu_trop_faible() -> None:
    assert "TU" in verifier({"TU": 50, "TI": 40, "E2E": 10})[0]


def test_verifier_refuse_ti_et_e2e_trop_forts() -> None:
    echecs = verifier({"TU": 65, "TI": 5, "E2E": 30})
    assert len(echecs) == 1 and "E2E" in echecs[0]
    assert "TI" in verifier({"TU": 65, "TI": 30, "E2E": 5})[0]


def test_verifier_refuse_niveau_vide() -> None:
    assert verifier({"TU": 9, "TI": 1, "E2E": 0})


def test_projets_absents_comptent_zero(tmp_path: Path) -> None:
    assert compter(tmp_path) == {"TU": 0, "TI": 0, "E2E": 0}


def test_tous_les_projets_python_sont_comptes() -> None:
    # un projet ajouté au monorepo sans être déclaré dans NIVEAUX fausserait la porte (#48)
    racine = Path(__file__).resolve().parents[2]
    comptes = {d for dossiers, _ in NIVEAUX.values() for d in dossiers}
    trouves = {
        p.relative_to(racine).as_posix()
        for p in racine.glob("*/tests/*")
        if p.name in ("unit", "integration")
    }
    assert trouves <= comptes, f"oubliés par la porte : {sorted(trouves - comptes)}"


def test_dotnet_ignore_version_du_ci(monkeypatch: pytest.MonkeyPatch) -> None:
    # #179 : VERSION (SHA) est lue comme la propriété MSBuild Version, la restauration échoue
    vus: dict[str, str] = {}

    def faux_run(
        _commande: list[str], **options: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        vus.update(options["env"])
        return subprocess.CompletedProcess([], 0, "  Un.Test\n  Un.Autre\nRésumé\n", "")

    monkeypatch.setenv("VERSION", "abc123")
    monkeypatch.setattr(pyramide.subprocess, "run", faux_run)
    assert pyramide._dotnet(Path("projet")) == 2
    assert "VERSION" not in vus


def test_dotnet_en_echec_arrete_la_porte_au_lieu_de_compter_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # #179 : un échec silencieux comptait 0 test C# et rendait la porte faussement verte
    monkeypatch.setattr(
        pyramide.subprocess,
        "run",
        lambda _c, **_o: subprocess.CompletedProcess([], 1, "", "MSB4181"),
    )
    with pytest.raises(RuntimeError, match="projet"):
        pyramide._dotnet(Path("projet"))


def test_seuil_ti_a_30_pour_cent() -> None:
    # #179 : services fins et contrats HTTP ; 30 % décidé par écrit, pas davantage
    assert verifier({"TU": 70, "TI": 29, "E2E": 1}) == []
    assert "TI" in verifier({"TU": 68, "TI": 31, "E2E": 1})[0]

