"""Évaluations de l'agent (``make eval``) : rejoue ``eval/golden.jsonl`` contre une API déployée.

Boîte noire : seul ``POST /api/agent`` est appelé, aucun secret Azure n'est nécessaire.
Chaque cas passe ses contrôles déterministes (``verifier``) et sa latence est mesurée. Le rapport
JSON s'ouvre sur un ``manifeste`` (commit, modèle, prompts, golden dataset, portes) : il dit ce qui
a été évalué. Code de sortie 1 si le taux de réussite est sous le seuil ou si la latence p95
dépasse son maximum : porte bloquante.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
import urllib.request
from datetime import UTC, datetime
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


def p95(valeurs: list[float]) -> float:
    """95e centile (rang le plus proche) : avec 5 cas, c'est le plus lent."""
    ordonnees = sorted(valeurs)
    return ordonnees[math.ceil(0.95 * len(ordonnees)) - 1]


def _sha256(chemin: Path) -> str:
    return hashlib.sha256(chemin.read_bytes()).hexdigest()


def _lire_env(chemin: Path) -> dict[str, str]:
    """Fichier KEY=VALUE (``llm.env``), sans dépendance : ce script tourne avec python3 seul."""
    valeurs = {}
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        cle, egal, valeur = ligne.strip().partition("=")
        if egal and not cle.startswith("#"):
            valeurs[cle.strip()] = valeur.strip()
    return valeurs


def _commit() -> str:
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    try:
        sortie = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
    except OSError:
        return "inconnu"
    return sortie.stdout.strip() or "inconnu"


def manifeste(
    url: str, golden: Path, prompts: Path, llm_env: Path, portes: dict[str, float]
) -> dict[str, Any]:
    """Ce qui est évalué : commit, modèle épinglé, prompts et golden dataset (empreintes)."""
    run = os.environ.get("GITHUB_RUN_ID")
    depot = os.environ.get("GITHUB_REPOSITORY")
    cas = [json.loads(ligne) for ligne in golden.read_text(encoding="utf-8").splitlines() if ligne]
    return {
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "commit": _commit(),
        "run": f"https://github.com/{depot}/actions/runs/{run}" if run and depot else None,
        "cible": url,
        "modele": {
            "fichier": str(llm_env),
            "deploiement": _lire_env(llm_env).get("AZURE_OPENAI_DEPLOYMENT"),
        },
        "prompts": [
            {"fichier": str(p), "sha256": _sha256(p), "contenu": p.read_text(encoding="utf-8")}
            for p in sorted(prompts.glob("*.md"))
        ],
        "golden": {
            "fichier": str(golden),
            "sha256": _sha256(golden),
            "cas": [c["id"] for c in cas],
        },
        "portes": portes,
    }


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
    # latence de l'évaluation p95 ≤ 30 s (dossier-conception-v1.md, D11)
    parser.add_argument("--latence-p95-max", type=float, default=30.0)
    parser.add_argument("--prompts", type=Path, default=Path("agentinsurflow/prompts"))
    parser.add_argument("--llm-env", type=Path, default=Path("llm.env"))
    parser.add_argument("--rapport", type=Path)
    args = parser.parse_args(argv)

    lignes = args.golden.read_text(encoding="utf-8").splitlines()
    resultats = []
    for cas in (json.loads(ligne) for ligne in lignes if ligne.strip()):
        debut = time.perf_counter()
        try:
            reponse = interroger(args.url, cas["question"])
        except (OSError, ValueError) as exc:  # réseau, HTTP ≠ 2xx, JSON illisible
            reponse = {"erreur": repr(exc)}
        latence = round(time.perf_counter() - debut, 2)
        resultats.append(
            {
                "id": cas["id"],
                "echecs": verifier(cas, reponse),
                "latence_s": latence,
                "reponse": reponse,
            }
        )

    taux = sum(not r["echecs"] for r in resultats) / len(resultats)
    latence_p95 = p95([r["latence_s"] for r in resultats])
    portes = {"seuil": args.seuil, "latence_p95_max_s": args.latence_p95_max}
    entete = manifeste(args.url, args.golden, args.prompts, args.llm_env, portes)
    # le modèle réellement servi par l'API, pour le comparer au modèle épinglé
    entete["modele"]["observe"] = sorted(
        {str(r["reponse"]["modele"]) for r in resultats if r["reponse"].get("modele")}
    )
    rapport = {
        "manifeste": entete,
        "taux": taux,
        "latence_p95_s": latence_p95,
        "resultats": resultats,
    }
    sortie = json.dumps(rapport, ensure_ascii=False, indent=2)
    print(sortie)
    if args.rapport:
        args.rapport.write_text(sortie, encoding="utf-8")
    qualite, rapidite = taux >= args.seuil, latence_p95 <= args.latence_p95_max
    print(f"{'✔' if qualite else '✘'} réussite {taux:.0%} (seuil {args.seuil:.0%})")
    print(f"{'✔' if rapidite else '✘'} latence p95 {latence_p95} s (max {args.latence_p95_max} s)")
    return 0 if qualite and rapidite else 1


if __name__ == "__main__":
    sys.exit(main())
