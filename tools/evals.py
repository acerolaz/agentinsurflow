"""Évaluations de l'agent (``make eval``) : rejoue ``eval/golden.jsonl`` contre une API déployée.

Boîte noire : seul ``POST /api/agent`` est appelé, aucun secret Azure n'est nécessaire.
Chaque cas passe ses contrôles déterministes (``verifier``). Le rapport JSON est versionnable
dans ``eval/preuves/``. Code de sortie 1 si le taux de réussite est sous le seuil : porte bloquante.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any

LONGUEUR_MAX = 600  # « trois phrases au plus » (prompt système de l'agent)


def verifier(cas: dict[str, Any], reponse: dict[str, Any]) -> list[str]:
    """Les contrôles ratés pour un cas ; une liste vide signifie que le cas est réussi."""
    texte = str(reponse.get("texte", ""))
    echecs = []
    if reponse.get("mode") != "llm":
        echecs.append("mode_llm")  # le LLM n'a pas répondu (repli ou erreur)
    if not texte.strip():
        echecs.append("non_vide")
    if len(texte) > cas.get("max_caracteres", LONGUEUR_MAX):
        echecs.append("longueur")
    attendus = cas.get("contient_un", [])
    if attendus and not any(mot.lower() in texte.lower() for mot in attendus):
        echecs.append("contient_un")
    return echecs


def interroger(url: str, question: str) -> dict[str, Any]:
    requete = urllib.request.Request(
        f"{url.rstrip('/')}/api/agent",
        data=json.dumps({"texte": question}).encode(),
        headers={"content-type": "application/json"},
    )
    with urllib.request.urlopen(requete, timeout=60) as reponse:
        resultat: dict[str, Any] = json.load(reponse)
        return resultat


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--golden", type=Path, default=Path("eval/golden.jsonl"))
    # ponytail: seuil de départ, 🔴 à calibrer sur plusieurs runs (comme la couverture, P4)
    parser.add_argument("--seuil", type=float, default=0.8)
    parser.add_argument("--rapport", type=Path)
    args = parser.parse_args(argv)

    lignes = args.golden.read_text(encoding="utf-8").splitlines()
    resultats = []
    for cas in (json.loads(ligne) for ligne in lignes if ligne.strip()):
        try:
            reponse = interroger(args.url, cas["question"])
        except (OSError, ValueError) as exc:  # réseau, HTTP ≠ 2xx, JSON illisible
            reponse = {"erreur": repr(exc)}
        resultats.append({"id": cas["id"], "echecs": verifier(cas, reponse), "reponse": reponse})

    taux = sum(not r["echecs"] for r in resultats) / len(resultats)
    rapport = {"url": args.url, "seuil": args.seuil, "taux": taux, "resultats": resultats}
    sortie = json.dumps(rapport, ensure_ascii=False, indent=2)
    print(sortie)
    if args.rapport:
        args.rapport.write_text(sortie, encoding="utf-8")
    print(f"{'✔' if taux >= args.seuil else '✘'} réussite {taux:.0%} (seuil {args.seuil:.0%})")
    return 0 if taux >= args.seuil else 1


if __name__ == "__main__":
    sys.exit(main())
