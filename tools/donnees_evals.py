"""Test des données d'évaluation (``make donnees-evals``), exécuté en CI avant les évaluations.

Déterministe et hors ligne : schéma de ``eval/golden.jsonl`` et ``eval/questions-demo.jsonl``,
articles attendus présents dans le dernier instantané Légifrance de ``data/raw``, et intégrité de
cet instantané (sha256 du manifeste, nombre d'articles). Affiche le sha256 de chaque fichier
contrôlé ; code de sortie 1 si une erreur est trouvée, chacune sur sa ligne préfixée ``✘``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from agentinsurflow_rag.cli.ingest import ErreurEnvoi, lire_instantane
from tools.evals import _article

CLES_CAS = {"id", "question", "attendu", "numero_contrat", "ci"}
CLES_ATTENDU = {"statut", "articles", "http"}
STATUTS = {"OK", "NOT_FOUND_IN_CORPUS"}


def _erreurs_cas(cas: Any) -> list[str]:
    """Les défauts de schéma d'un cas déjà décodé (hors unicité de l'``id``)."""
    if not isinstance(cas, dict):
        return ["le cas doit être un objet JSON"]
    erreurs = [f"clé inconnue : {c}" for c in cas if c not in CLES_CAS]
    for champ in ("id", "question"):
        if not isinstance(cas.get(champ), str) or not cas[champ].strip():
            erreurs.append(f"{champ} : chaîne non vide requise")
    if "attendu" not in cas:
        return erreurs
    attendu = cas["attendu"]
    if not isinstance(attendu, dict):
        return [*erreurs, "attendu : objet requis"]
    erreurs += [f"attendu : clé inconnue : {c}" for c in attendu if c not in CLES_ATTENDU]
    if "statut" in attendu and attendu["statut"] not in STATUTS:
        erreurs.append(f"statut : {sorted(STATUTS)} attendu")
    articles = attendu.get("articles", [])
    if not isinstance(articles, list) or not all(isinstance(a, str) for a in articles):
        erreurs.append("articles : liste de chaînes requise")
    http = attendu.get("http", 0)
    if not isinstance(http, int) or isinstance(http, bool):
        erreurs.append("http : entier requis")
    return erreurs


def controler_cas(lignes: list[str], fichier: str) -> list[str]:
    """Les erreurs ``fichier:n° raison`` (n° 1-based, lignes vides ignorées mais comptées)."""
    erreurs: list[str] = []
    vus: set[str] = set()
    for n, ligne in enumerate(lignes, start=1):
        if not ligne.strip():
            continue
        try:
            cas = json.loads(ligne)
        except json.JSONDecodeError as e:
            erreurs.append(f"{fichier}:{n} JSON invalide : {e.msg}")
            continue
        raisons = _erreurs_cas(cas)
        identifiant = cas.get("id") if isinstance(cas, dict) else None
        if isinstance(identifiant, str) and identifiant:
            if identifiant in vus:
                raisons.append(f"id en double : {identifiant}")
            vus.add(identifiant)
        erreurs += [f"{fichier}:{n} {r}" for r in raisons]
    return erreurs


def articles_manquants(cas: list[dict[str, Any]], connus: set[str]) -> list[str]:
    """Un message par article attendu absent de l'instantané (``connus`` déjà normalisés)."""
    return [
        f"{c.get('id')} : article {a} absent de l'instantané"
        for c in cas
        for a in c.get("attendu", {}).get("articles", [])
        if _article(a) not in connus
    ]


def dernier_instantane(dossier: Path) -> Path:
    return sorted(dossier.glob("code-assurances-*.json"))[-1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Teste les données d'évaluation (hors ligne).")
    parser.add_argument("--golden", type=Path, default=Path("eval/golden.jsonl"))
    parser.add_argument("--questions", type=Path, default=Path("eval/questions-demo.jsonl"))
    parser.add_argument("--instantanes", type=Path, default=Path("data/raw"))
    args = parser.parse_args(argv)

    erreurs: list[str] = []
    cas: list[dict[str, Any]] = []
    for fichier in (args.golden, args.questions):
        try:
            octets = fichier.read_bytes()
            lignes = octets.decode("utf-8").split("\n")
        except (OSError, UnicodeDecodeError) as e:
            erreurs.append(f"{fichier} : illisible ({e})")
            continue
        print(f"{hashlib.sha256(octets).hexdigest()}  {fichier}")
        erreurs_fichier = controler_cas(lignes, str(fichier))
        erreurs += erreurs_fichier
        if not erreurs_fichier:  # sinon le schéma est déjà signalé : pas de cas à confronter
            cas += [json.loads(ligne) for ligne in lignes if ligne.strip()]

    try:
        instantane = dernier_instantane(args.instantanes)
    except IndexError:
        erreurs.append(f"{args.instantanes} : aucun instantané code-assurances-*.json")
    else:
        try:
            articles, sha, _ = lire_instantane(instantane)
            manifeste = json.loads(instantane.read_text(encoding="utf-8"))["manifeste"]
            print(f"{sha}  {instantane}")
            attendus = manifeste["articles"]
            if len(articles) != attendus:
                erreurs.append(f"{instantane} : {len(articles)} articles ≠ {attendus} du manifeste")
            erreurs += articles_manquants(cas, {_article(a["article"]) for a in articles})
        except ErreurEnvoi as e:
            erreurs.append(f"{instantane} : {e}")
        except (OSError, ValueError, KeyError, TypeError) as e:
            erreurs.append(f"{instantane} : instantané illisible ou mal formé ({e!r})")

    for erreur in erreurs:
        print(f"✘ {erreur}")
    return 1 if erreurs else 0


if __name__ == "__main__":
    raise SystemExit(main())
