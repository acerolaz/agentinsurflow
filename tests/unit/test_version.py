"""Unitaires — calcul du tag de release vX.Y.Z, sans Git."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools import version


@pytest.mark.parametrize(
    ("base", "tags", "attendu"),
    [
        ("0.1.0", [], "v0.1.0"),  # premier tag de la série
        ("0.1.0", ["v0.1.0"], "v0.1.1"),  # Z suit les tags existants
        ("0.1.0", ["v0.1.9", "v0.1.10", "v0.1.2"], "v0.1.11"),  # tri numérique, pas alphabétique
        ("0.2.0", ["v0.1.4"], "v0.2.0"),  # X.Y relevé à la main dans le pyproject
        ("0.1.0", ["v0.10.3", "v0.1.0-rc", "autre"], "v0.1.0"),  # tags d'autres séries ignorés
    ],
)
def test_prochaine_release(base: str, tags: list[str], attendu: str) -> None:
    assert version.prochaine_release(base, tags) == attendu


def test_version_projet(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nversion = "1.2.3"\n', encoding="utf-8")
    assert version.version_projet(pyproject) == "1.2.3"
