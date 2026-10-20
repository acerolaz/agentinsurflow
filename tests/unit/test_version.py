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
        ("0.10.0", ["v0.1.5", "v0.10.0-rc", "autre"], "v0.10.0"),  # v0.1.5 hors série v0.10.
    ],
)
def test_prochaine_release(base: str, tags: list[str], attendu: str) -> None:
    assert version.prochaine_release(base, tags) == attendu


def test_un_pyproject_sous_la_derniere_release_est_refuse() -> None:
    with pytest.raises(ValueError, match="v0.4.0"):
        version.prochaine_release("0.3.0", ["v0.2.0", "v0.4.0"])


@pytest.mark.parametrize(
    ("en_service", "livree"),
    [
        ("v0.2.0", "v0.4.0"),  # montée de série
        ("v0.4.0", "v0.4.1"),  # patch suivant
        ("v0.4.9", "v0.4.10"),  # tri numérique, pas alphabétique
        ("v0.4.0", "v0.4.0"),  # relance du même déploiement : même tag, donc même commit
        (None, "v0.1.0"),  # premier déploiement : aucune release en service
    ],
)
def test_livraison_croissante_acceptee(en_service: str | None, livree: str) -> None:
    version.verifier_livraison(en_service, livree)


@pytest.mark.parametrize(("en_service", "livree"), [("v0.4.0", "v0.2.0"), ("v0.4.10", "v0.4.9")])
def test_livraison_inferieure_refusee(en_service: str, livree: str) -> None:
    with pytest.raises(ValueError, match="rollback"):
        version.verifier_livraison(en_service, livree)


def test_version_projet(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nversion = "1.2.3"\n', encoding="utf-8")
    assert version.version_projet(pyproject) == "1.2.3"
