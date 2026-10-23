"""TU — règle de dépendance hexagonale, vérifiée sur les imports (ast)."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

PAQUET = Path(__file__).resolve().parents[2] / "agentinsurflow_cluster"
AUTORISES = sys.stdlib_module_names | {"agentinsurflow_cluster"}
INTERDITS = (
    "fastapi",
    "pydantic",
    "langchain",
    "langgraph",
    "llm_guard",
    "opentelemetry",
    "httpx",
    "mcp",
    "azure",
)


def _imports(couche: str) -> set[str]:
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
                modules.add(".".join(p for p in (base, noeud.module or "") if p))
    return modules


# ponytail: `application/` n'existe qu'à partir de la tâche 8 ; couches présentes seulement
COUCHES = [c for c in ("domain", "application") if (PAQUET / c).is_dir()]


@pytest.mark.parametrize("couche", COUCHES)
def test_couche_sans_dependance_externe(couche: str) -> None:
    assert {m for m in _imports(couche) if m.split(".")[0] not in AUTORISES} == set()


@pytest.mark.parametrize("couche", COUCHES)
def test_aucun_import_interdit(couche: str) -> None:
    assert {m for m in _imports(couche) if m.split(".")[0] in INTERDITS} == set()


def test_domain_n_importe_ni_application_ni_infrastructure_ni_api() -> None:
    interdits = tuple(
        f"agentinsurflow_cluster.{c}" for c in ("application", "infrastructure", "api")
    )
    assert {m for m in _imports("domain") if m.startswith(interdits)} == set()
