"""Tag de release ``vX.Y.Z``, posé sur le commit juste avant la production (job release).

X.Y se choisissent à la main dans ``pyproject.toml`` ; Z est calculé d'après les tags existants
(``v0.1.0``, puis ``v0.1.1``…). Passer le pyproject à 0.2.0 donne ``v0.2.0``.
``python3 tools/version.py`` affiche le tag à poser sur ``HEAD`` : celui qu'il porte déjà s'il en a
un, pour qu'une relance ne crée pas de second tag.

Hors rollback, une version livrée dépasse la précédente : la série du pyproject ne descend pas
sous la dernière release, et ``python3 tools/version.py --verifier <en service> <livrée>`` (appelé
par deploy.yml avant la production) refuse une release inférieure à celle en service.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

RELEASE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def version_projet(pyproject: Path = Path("pyproject.toml")) -> str:
    return str(tomllib.loads(pyproject.read_text())["project"]["version"])


def _cle(tag: str) -> tuple[int, ...]:
    trouve = RELEASE.match(tag)
    if not trouve:
        raise ValueError(f"release illisible : {tag!r} (attendu vX.Y.Z)")
    return tuple(int(n) for n in trouve.groups())


def prochaine_release(base: str, tags: list[str]) -> str:
    """Tag suivant pour la série X.Y de ``base`` ; ``tags`` = tags Git existants."""
    releases = [t for t in tags if RELEASE.match(t)]
    derniere = max(releases, key=_cle, default=None)
    if derniere and _cle(f"v{base}")[:2] < _cle(derniere)[:2]:
        raise ValueError(f"pyproject {base} sous la dernière release {derniere} : relever X.Y")
    serie = f"v{base.rsplit('.', 1)[0]}."
    patchs = [int(z) for t in tags if (z := t.removeprefix(serie)) != t and z.isdigit()]
    return f"{serie}{max(patchs) + 1}" if patchs else f"v{base}"


def verifier_livraison(en_service: str | None, livree: str) -> None:
    """Hors rollback, la release livrée ne descend pas sous celle en service.

    Égale = relance du même déploiement : un tag de release ne désigne qu'un commit.
    """
    if en_service and _cle(livree) < _cle(en_service):
        raise ValueError(
            f"{livree} est sous {en_service}, en service : seul un rollback "
            "(deploy.yml lancé à la main, make rollback) peut revenir en arrière"
        )


def _git(*args: str) -> list[str]:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout.split()


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    try:
        if args[:1] == ["--verifier"]:
            en_service, livree = args[1:3]
            verifier_livraison(en_service or None, livree)
            print(f"✔ {livree} ≥ {en_service or 'aucune release en service'}")
            return 0
        deja = _git("tag", "--points-at", "HEAD", "--list", "v*")
        print(deja[0] if deja else prochaine_release(version_projet(), _git("tag", "--list", "v*")))
        return 0
    except ValueError as exc:
        print(f"✘ {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
