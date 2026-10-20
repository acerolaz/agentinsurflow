"""Unitaires — la porte de la pyramide de tests (70 / 20 / 10, S3-22), sans lancer de tests."""

from __future__ import annotations

from pathlib import Path

from tools.pyramide import compter, verifier


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
