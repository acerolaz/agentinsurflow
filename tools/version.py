"""Tag de release ``vX.Y.Z``, posé sur le commit juste avant la production (job release).

X.Y se choisissent à la main dans ``pyproject.toml`` ; Z est calculé d'après les tags existants
(``v0.1.0``, puis ``v0.1.1``…). Passer le pyproject à 0.2.0 donne ``v0.2.0``.
``python3 tools/version.py`` affiche le tag à poser sur ``HEAD`` : celui qu'il porte déjà s'il en a
un, pour qu'une relance ne crée pas de second tag.
"""

from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path


def version_projet(pyproject: Path = Path("pyproject.toml")) -> str:
    return str(tomllib.loads(pyproject.read_text())["project"]["version"])


def prochaine_release(base: str, tags: list[str]) -> str:
    """Tag suivant pour la série X.Y de ``base`` ; ``tags`` = tags Git existants."""
    serie = f"v{base.rsplit('.', 1)[0]}."
    patchs = [int(z) for t in tags if (z := t.removeprefix(serie)) != t and z.isdigit()]
    return f"{serie}{max(patchs) + 1}" if patchs else f"v{base}"


def _git(*args: str) -> list[str]:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout.split()


def main() -> None:
    deja = _git("tag", "--points-at", "HEAD", "--list", "v*")
    print(deja[0] if deja else prochaine_release(version_projet(), _git("tag", "--list", "v*")))


if __name__ == "__main__":
    main()
