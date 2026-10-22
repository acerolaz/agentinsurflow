"""Unitaires — règle de dépendance de l'architecture hexagonale, vérifiée sur les imports (ast).

``domain`` et ``application`` n'importent que la bibliothèque standard et les couches intérieures.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

PAQUET = Path(__file__).resolve().parents[2] / "agentinsurflow_mcp"
AUTORISES = sys.stdlib_module_names | {"agentinsurflow_mcp"}  # stdlib + couches du paquet


def _imports(couche: str) -> set[str]:
    """Modules importés par les fichiers d'une couche (chemins absolus, relatifs résolus)."""
    fichiers = sorted((PAQUET / couche).rglob("*.py"))
    assert fichiers, f"couche {couche} absente"
    modules: set[str] = set()
    for fichier in fichiers:
        paquet = ".".join(fichier.relative_to(PAQUET.parent).with_suffix("").parts[:-1])
        for noeud in ast.walk(ast.parse(fichier.read_text(encoding="utf-8"))):
            if isinstance(noeud, ast.Import):
                modules.update(alias.name for alias in noeud.names)
            elif isinstance(noeud, ast.ImportFrom):
                base = paquet.rsplit(".", noeud.level - 1)[0] if noeud.level else ""
                cible = ".".join(p for p in (base, noeud.module or "") if p)
                modules.add(cible)
    return modules


@pytest.mark.parametrize("couche", ["domain", "application"])
def test_couche_sans_dependance_externe(couche: str) -> None:
    assert {m for m in _imports(couche) if m.split(".")[0] not in AUTORISES} == set()


def test_domain_n_importe_ni_application_ni_infrastructure_ni_api() -> None:
    interdits = {f"agentinsurflow_mcp.{c}" for c in ("application", "infrastructure", "api")}
    assert {m for m in _imports("domain") if m.startswith(tuple(interdits))} == set()


def test_application_n_importe_ni_infrastructure_ni_api() -> None:
    interdits = {f"agentinsurflow_mcp.{c}" for c in ("infrastructure", "api")}
    assert {m for m in _imports("application") if m.startswith(tuple(interdits))} == set()
