"""Instantané versionné du barème : REGLES → data/raw/bareme-<version>.json.

Hors de `domain/` : il écrit un fichier. Sortie déterministe (aucune date du jour) ;
lu par le paquet `rag` par le fichier seul, jamais par import.
"""

import argparse
import hashlib
import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from agentinsurflow_calcul.domain.bareme import DATE_BAREME, REGLES, VERSION_BAREME


def _sha(regles: list[dict[str, Any]]) -> str:
    """SHA-256 du JSON canonique (clés triées, sans espaces), comme le code des assurances."""
    canonique = json.dumps(regles, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonique.encode("utf-8")).hexdigest()


def serialiser() -> dict[str, Any]:
    regles = [
        {
            "regle_id": r.regle_id,
            "libelle": r.libelle,
            "conditions": [
                {"champ": c.champ, "operateur": c.operateur, "seuil": str(c.seuil)}
                for c in r.conditions
            ],
            "motif": r.motif,
            "effet": r.effet,
        }
        for r in REGLES
    ]
    return {
        "manifeste": {
            "version_bareme": VERSION_BAREME,
            "date_debut": DATE_BAREME,
            "regles": len(regles),
            "sha256": _sha(regles),
        },
        "regles": regles,
    }


def ecrire(dossier: Path) -> Path:
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / f"{VERSION_BAREME}.json"
    temporaire = chemin.with_suffix(".json.tmp")
    temporaire.write_text(json.dumps(serialiser(), ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(temporaire, chemin)  # atomique : jamais d'instantané partiel
    return chemin


def main(argv: Sequence[str] | None = None) -> int:
    parseur = argparse.ArgumentParser(description="Écrit l'instantané versionné du barème.")
    parseur.add_argument("--dossier", type=Path, default=Path("data/raw"))
    chemin = ecrire(parseur.parse_args(argv).dossier)
    print(f"✔ {chemin} ({len(REGLES)} règles)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
