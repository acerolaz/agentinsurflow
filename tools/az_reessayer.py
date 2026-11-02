#!/usr/bin/env python3
"""Rejoue une commande ``az`` sur erreur passagère d'Azure (#135).

    python3 tools/az_reessayer.py az containerapp update -n APP -g RG --yaml FICHIER

Bibliothèque standard seule : lancé tel quel sur le runner, avant toute installation.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from subprocess import CompletedProcess

TENTATIVES = 3
PAUSE_S = 30.0
PASSAGERE = re.compile(
    r"ServerTimeout|GatewayTimeout|TooManyRequests|Service Unavailable|Bad Gateway|timed out"
    r"|\b(429|502|503|504)\b"
)

Executeur = Callable[[list[str]], CompletedProcess[str]]


def _lancer(commande: list[str]) -> CompletedProcess[str]:
    return subprocess.run(commande, capture_output=True, text=True, check=False)


def _option(commande: list[str], nom: str) -> str | None:
    return commande[commande.index(nom) + 1] if nom in commande[:-1] else None


def _deja_applique(commande: list[str], azure: Executeur) -> bool:
    """Après un ServerTimeout : l'application porte-t-elle déjà l'image et le DEPLOIEMENT voulus ?"""
    fichier, app, groupe = (_option(commande, o) for o in ("--yaml", "-n", "-g"))
    if commande[:3] != ["az", "containerapp", "update"] or not (fichier and app and groupe):
        return False
    attendu = Path(fichier).read_text(encoding="utf-8")
    image = re.search(r"^\s*image:\s*(\S+)", attendu, re.M)
    deploiement = re.search(r'name:\s*DEPLOIEMENT,\s*value:\s*"([^"]*)"', attendu)
    lu = azure(["az", "containerapp", "show", "-n", app, "-g", groupe, "-o", "json"])
    if lu.returncode != 0 or image is None:
        return False
    # ponytail: seuls l'image et DEPLOIEMENT sont comparés, un autre écart de YAML passerait
    conteneur = json.loads(lu.stdout)["properties"]["template"]["containers"][0]
    variables = {v["name"]: v.get("value") for v in conteneur.get("env", [])}
    return conteneur["image"] == image[1] and (
        deploiement is None or variables.get("DEPLOIEMENT") == deploiement[1]
    )


def executer(
    commande: list[str], azure: Executeur = _lancer, pause: Callable[[float], None] = time.sleep
) -> int:
    code = 1
    for tentative in range(1, TENTATIVES + 1):
        resultat = azure(commande)
        sys.stdout.write(resultat.stdout)
        sys.stderr.write(resultat.stderr)
        code = resultat.returncode
        if code == 0 or not PASSAGERE.search(resultat.stderr):
            return code
        cause = PASSAGERE.search(resultat.stderr)[0]  # type: ignore[index]
        print(f"::warning::az : erreur passagère « {cause} », tentative {tentative}/{TENTATIVES}")
        if cause == "ServerTimeout" and _deja_applique(commande, azure):
            print("::notice::az : la mise à jour demandée est déjà appliquée, pas de nouvel essai")
            return 0
        if tentative < TENTATIVES:
            pause(PAUSE_S)
    print(f"::error::az : tentatives épuisées, voir docs/rollback.md : {' '.join(commande[:3])}")
    return code


if __name__ == "__main__":
    sys.exit(executer(sys.argv[1:]))
