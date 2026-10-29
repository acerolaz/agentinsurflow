"""Agrège Légifrance, notices et procédures générées du barème en UN jeu brut versionné.

    uv run python -m agentinsurflow_rag.cli.agreger

Sortie ``data/aggregated/corpus-<date Légifrance>.json`` : octet pour octet identique à chaque
relance (aucune date du jour). Les articles abrogés sont conservés ; seules les entrées corrompues
sont écartées, avec leur raison, dans le manifeste.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ..domain.corpus import nettoyer
from ..domain.models import Rejet
from ..domain.procedures import ErreurProcedures, generer
from .ingest import (
    COLLECTIONS,
    URL_DEPOT,
    ErreurEnvoi,
    lire_en_tete,
    lire_instantane,
    lire_markdown,
    sha_articles,
)

SOURCES = ("legifrance", "redige", "bareme")


def normaliser(brut: Mapping[str, Any]) -> dict[str, Any] | str:
    """Entrée normalisée (formats homogènes, état et HTML d'origine), ou la raison de l'écart."""
    etat = str(brut.get("etat") or "").strip()
    if not etat:
        return "partiel:etat"
    # l'état n'est pas un critère de qualité ici : un abrogé reste au jeu, on valide le reste
    propre = nettoyer({**brut, "etat": "VIGUEUR"})
    if isinstance(propre, Rejet):
        return propre.raison
    return {
        "doc_id": propre.doc_id,
        "version": propre.version,
        "article": propre.article,
        "date_debut": propre.date_debut.isoformat() if propre.date_debut else None,
        "etat": etat.upper(),
        "texte_html": brut["texte_html"],
        "url_source": propre.url_source,
        "regle_id": propre.regle_id,
        "collection": brut.get("collection"),
        "source": brut.get("source"),
    }


def _lire_bareme(chemin: Path) -> tuple[dict[str, Any], str]:
    bareme = json.loads(chemin.read_text(encoding="utf-8"))
    sha = sha_articles(bareme["regles"])
    if sha != bareme["manifeste"]["sha256"]:
        raise ErreurEnvoi(f"instantané du barème altéré : sha256 {sha} ≠ manifeste")
    return bareme, sha


def agreger(legifrance: Path, bareme: Path, notices: Path, procedures: Path) -> dict[str, Any]:
    articles, sha_legifrance, jour = lire_instantane(legifrance)
    regles, sha_bareme = _lire_bareme(bareme)
    rediges = {}
    for fichier in sorted(procedures.glob("*.md")):
        en_tete, corps = lire_en_tete(fichier)
        if not en_tete.get("regle_id"):
            raise ErreurEnvoi(f"{fichier.name} : en-tête sans regle_id")
        rediges[en_tete["regle_id"]] = corps
    bruts = (
        [{**a, "collection": COLLECTIONS[0], "source": SOURCES[0]} for a in articles]
        + [
            {**n, "collection": COLLECTIONS[1], "source": SOURCES[1]}
            for n in lire_markdown(notices, COLLECTIONS[1])
        ]
        + [
            {**p, "collection": COLLECTIONS[2], "source": SOURCES[2]}
            for p in generer(regles, rediges, URL_DEPOT)
        ]
    )
    entrees: list[dict[str, Any]] = []
    ecarts: list[dict[str, Any]] = []
    vus: set[tuple[str, str]] = set()
    for brut in bruts:
        resultat = normaliser(brut)
        if isinstance(resultat, str):
            ecarts.append(
                {"doc_id": brut.get("doc_id"), "source": brut["source"], "raison": resultat}
            )
            continue
        # un même doc_id peut porter plusieurs versions (A211-1-3 : vigueur + abrogée)
        cle = (resultat["doc_id"], resultat["version"])
        if cle in vus:
            raise ErreurEnvoi(f"doc_id en double : {cle[0]} (version {cle[1]})")
        vus.add(cle)
        entrees.append(resultat)
    manifeste = {
        "date": jour.isoformat(),
        "entrees": len(entrees),
        "par_collection": {c: sum(e["collection"] == c for e in entrees) for c in COLLECTIONS},
        "par_source": {s: sum(e["source"] == s for e in entrees) for s in SOURCES},
        "sources": {"legifrance": sha_legifrance, "bareme": sha_bareme},
        "ecarts": ecarts,
        "sha256": sha_articles(entrees),
    }
    return {"manifeste": manifeste, "entrees": entrees}


def ecrire_jeu(jeu: Mapping[str, Any], dossier: Path) -> Path:
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / f"corpus-{jeu['manifeste']['date']}.json"
    temporaire = chemin.with_suffix(".json.tmp")
    temporaire.write_text(json.dumps(jeu, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(temporaire, chemin)  # atomique : jamais de jeu partiel
    return chemin


def _dernier(motif: str) -> Path:
    trouves = sorted(Path("data/raw").glob(motif))
    if not trouves:
        raise ErreurEnvoi(f"aucun instantané data/raw/{motif}")
    return trouves[-1]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legifrance", type=Path)
    parser.add_argument("--bareme", type=Path)
    parser.add_argument("--notices", type=Path, default=Path("rag/corpus/notices_produits"))
    parser.add_argument("--procedures", type=Path, default=Path("rag/corpus/procedures_internes"))
    parser.add_argument("--dossier", type=Path, default=Path("data/aggregated"))
    args = parser.parse_args(argv)
    try:
        jeu = agreger(
            args.legifrance or _dernier("code-assurances-*.json"),
            args.bareme or _dernier("bareme-*.json"),
            args.notices,
            args.procedures,
        )
        chemin = ecrire_jeu(jeu, args.dossier)
    except (ErreurEnvoi, ErreurProcedures, OSError, KeyError, ValueError) as exc:
        print(f"✘ {exc}", file=sys.stderr)
        return 1
    m = jeu["manifeste"]
    print(f"✔ {chemin} ({m['entrees']} entrées, {len(m['ecarts'])} écarts)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
