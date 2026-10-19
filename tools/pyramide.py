"""Porte de la pyramide de tests (S3-22) : 70 % TU, 20 % TI, 10 % E2E, en nombre de tests.

Compte ``rag``, ``underwriting-admin`` et ``e2e/`` ; la gateway (forme diamant) est comptée à part.
Échoue si TU < 65 %, TI > 25 %, E2E > 15 %, ou si un niveau est vide.

Usage : ``python tools/pyramide.py`` (depuis la racine du monorepo).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# niveau → (dossiers pytest, motifs des projets de tests C# sous underwriting-admin/tests)
NIVEAUX: dict[str, tuple[list[str], list[str]]] = {
    "TU": (["rag/tests/unit"], ["*.Domain.Tests", "*.Application.Tests"]),
    "TI": (["rag/tests/integration"], ["*.Infrastructure.Tests", "*.Api.Tests"]),
    "E2E": (["e2e"], []),
}
TESTS_CSHARP = "underwriting-admin/tests"
MIN_TU, MAX_TI, MAX_E2E = 65, 25, 15  # en % du total


def _pytest(racine: Path, dossier: Path) -> int:
    sortie = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "--no-cov", str(dossier)],
        capture_output=True,
        text=True,
        cwd=racine,
    )
    return sum("::" in ligne for ligne in sortie.stdout.splitlines())


def _dotnet(projet: Path) -> int:
    sortie = subprocess.run(
        ["dotnet", "test", "--project", str(projet), "--list-tests"],
        capture_output=True,
        text=True,
    )
    # ponytail: une ligne indentée par test (format --list-tests de Microsoft.Testing.Platform),
    # à confirmer quand underwriting-admin existera (Task U1)
    return sum(
        ligne.startswith("  ") and bool(ligne.strip()) for ligne in sortie.stdout.splitlines()
    )


def compter(racine: Path = Path(".")) -> dict[str, int]:
    """Nombre de tests par niveau ; un projet absent compte 0, sans erreur."""
    compte = {}
    for niveau, (dossiers, motifs) in NIVEAUX.items():
        n = sum(_pytest(racine, racine / d) for d in dossiers if (racine / d).is_dir())
        for motif in motifs:
            n += sum(_dotnet(p) for p in sorted((racine / TESTS_CSHARP).glob(motif)) if p.is_dir())
        compte[niveau] = n
    return compte


def verifier(compte: dict[str, int]) -> list[str]:
    """Les écarts aux seuils, dans l'ordre TU, TI, E2E ; une liste vide signifie conforme."""
    total = sum(compte.values()) or 1
    bornes = {"TU": (MIN_TU, 100), "TI": (0, MAX_TI), "E2E": (0, MAX_E2E)}
    echecs = []
    for niveau, (bas, haut) in bornes.items():
        part = 100 * compte.get(niveau, 0) / total
        if not compte.get(niveau):
            echecs.append(f"{niveau} : aucun test")
        elif not bas <= part <= haut:
            echecs.append(f"{niveau} : {part:.0f} % hors de [{bas} %, {haut} %]")
    return echecs


def main() -> int:
    compte = compter()
    total = sum(compte.values()) or 1
    for niveau, n in compte.items():
        print(f"{niveau:>4} : {n:4d} tests ({100 * n / total:.0f} %)")
    echecs = verifier(compte)
    for echec in echecs:
        print(f"✘ {echec}")
    print("✔ pyramide conforme (70 / 20 / 10)" if not echecs else "✘ pyramide hors seuils")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
