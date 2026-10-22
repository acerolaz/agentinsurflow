"""Unitaires — règle de dépendance hexagonale de la Function, vérifiée sur les imports (ast).

``domain`` n'importe que la bibliothèque standard et le paquet lui-même.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

PAQUET = Path(__file__).resolve().parents[2] / "agentinsurflow_calcul"
AUTORISES = sys.stdlib_module_names | {"agentinsurflow_calcul"}


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


def test_domain_sans_dependance_externe() -> None:
    assert {m for m in _imports("domain") if m.split(".")[0] not in AUTORISES} == set()
