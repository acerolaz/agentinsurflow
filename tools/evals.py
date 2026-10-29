"""Évaluations de l'agent (``make eval``) : rejoue ``eval/golden.jsonl`` (et, avec ``--questions``,
le jeu de démo ``eval/questions-demo.jsonl``) contre une API déployée. Python 3 seul, sans
dépendance (le job « changements » de la CI l'importe tel quel).

Boîte noire : seuls ``POST /api/reponses``, ``GET /api/extraits`` et ``/health`` sont appelés,
avec le jeton de ``EVALS_JETON`` (rôle ``Gestionnaire``) ; aucun secret Azure n'est nécessaire.
Chaque cas passe ses contrôles déterministes (``verifier`` : contrat RAG ``statut``, ``articles``,
``http`` ; réponse non vide, trois phrases au plus) et sa latence est mesurée. Le rapport JSON
s'ouvre sur un ``manifeste`` (commit, modèle, prompts, golden dataset, questions, corpus, portes) :
il dit ce qui a été évalué. Code de sortie 1 si le taux de réussite est sous le seuil ou si la
latence p95 dépasse son maximum : porte bloquante.

``--calibrer`` (``make calibrer``) affiche le cosinus max de chaque question, couvertes et hors
corpus séparées, et propose l'intervalle où choisir ``RAG_SEUIL`` (spec §4.1).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LONGUEUR_MAX = 600  # « trois phrases au plus » (prompt système de l'agent)
# ponytail: fenêtre fixe de la gateway (RateLimit:FenetreSecondes, 10 POST /api/reponses par
# minute) ; lire Retry-After si la fenêtre devient configurable par environnement
ATTENTE_429_S = 60.0


def _article(numero: str) -> str:
    """« L. 211-1 » → « L211-1 » (même normalisation que le domaine de rag)."""
    return re.sub(r"[\s.]", "", numero).upper()


def verifier(cas: dict[str, Any], reponse: dict[str, Any], http: int = 200) -> list[str]:
    """Les contrôles ratés pour un cas ; une liste vide signifie que le cas est réussi."""
    attendu = cas.get("attendu", {})
    if http != attendu.get("http", 200):
        return ["http"]
    if http != 200:
        return []  # refus attendu au niveau HTTP (BOLA : 404) ; le corps est un ProblemDetails
    texte = str(reponse.get("texte", ""))
    statut = attendu.get("statut")
    echecs = []
    if statut in (None, "OK") and reponse.get("mode") != "llm":
        echecs.append("mode_llm")  # le LLM n'a pas répondu (repli, refus ou erreur)
    if statut and reponse.get("statut") != statut:
        echecs.append("statut")
    articles = {_article(a) for a in attendu.get("articles", [])}
    cites = {_article(str(c.get("article", ""))) for c in reponse.get("citations", [])}
    if articles and not articles & cites:
        echecs.append("articles")  # au moins un des articles attendus doit être cité
    if not texte.strip():
        echecs.append("non_vide")
    if len(texte) > LONGUEUR_MAX:
        echecs.append("longueur")
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


def version_manifeste(pyproject: Path = Path("pyproject.toml")) -> str:
    """``X.Y.Z-build.N`` : version du pyproject + n° de run GitHub ; ``X.Y.Z-local`` hors CI."""
    base = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]
    run = os.environ.get("GITHUB_RUN_NUMBER")
    return f"{base}-build.{run}" if run else f"{base}-local"


def _jsonl(chemin: Path) -> list[dict[str, Any]]:
    return [json.loads(ligne) for ligne in chemin.read_text(encoding="utf-8").splitlines() if ligne]


def lire_cas(golden: Path, questions: Path | None = None) -> list[dict[str, Any]]:
    return _jsonl(golden) + (_jsonl(questions) if questions else [])


def manifeste(
    url: str,
    golden: Path,
    prompts: Path,
    llm_env: Path,
    portes: dict[str, float],
    questions: Path | None = None,
) -> dict[str, Any]:
    """Ce qui est évalué : commit, modèle épinglé, prompts, golden dataset, questions, corpus."""
    run = os.environ.get("GITHUB_RUN_ID")
    depot = os.environ.get("GITHUB_REPOSITORY")
    return {
        "version": version_manifeste(),
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
            "cas": [c["id"] for c in lire_cas(golden)],
        },
        "questions": None
        if questions is None
        else {
            "fichier": str(questions),
            "sha256": _sha256(questions),
            "cas": [c["id"] for c in _jsonl(questions)],
        },
        "corpus": corpus(url),  # dernier instantané ingéré et nombre de chunks (/health)
        "portes": portes,
    }


def _appeler(
    url: str, chemin: str, jeton: str | None, corps: dict[str, Any] | None = None
) -> tuple[int, dict[str, Any]]:
    """Code HTTP et corps JSON ; une réponse ≠ 2xx est rendue, pas levée (BOLA : 404 attendu)."""
    entetes = {"content-type": "application/json"}
    if jeton:
        entetes["Authorization"] = f"Bearer {jeton}"
    requete = urllib.request.Request(
        f"{url.rstrip('/')}{chemin}",
        data=None if corps is None else json.dumps(corps).encode(),
        headers=entetes,
    )
    try:
        with urllib.request.urlopen(requete, timeout=60) as reponse:
            return reponse.status, json.load(reponse)
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.load(exc)
        except ValueError:
            return exc.code, {}


def interroger(url: str, cas: dict[str, Any], jeton: str | None) -> tuple[int, dict[str, Any]]:
    corps = {"texte": cas["question"], "numero_contrat": cas.get("numero_contrat")}
    return _appeler(url, "/api/reponses", jeton, corps)


def extraits(url: str, question: str, jeton: str | None) -> dict[str, Any]:
    parametres = urllib.parse.urlencode({"question": question})
    return _appeler(url, f"/api/extraits?{parametres}", jeton)[1]


def corpus(url: str) -> dict[str, Any] | None:
    """Corpus servi par rag : ``/health/rag`` derrière la gateway, ``/health`` en direct."""
    for chemin in ("/health/rag", "/health"):
        try:
            http, sante = _appeler(url, chemin, None)
        except (OSError, ValueError):
            continue
        etat: dict[str, Any] | None = sante.get("corpus")
        if http == 200 and etat is not None:
            return etat
    return None


def calibrer(url: str, cas: list[dict[str, Any]], jeton: str | None) -> None:
    """Cosinus max par question (couvertes / hors corpus) et intervalle possible pour le seuil."""
    lignes = []
    for c in cas:
        statut = c.get("attendu", {}).get("statut")
        if statut not in ("OK", "NOT_FOUND_IN_CORPUS"):
            continue  # BOLA ou cas sans statut attendu : sans rapport avec la porte
        mesure = extraits(url, c["question"], jeton)
        type_ = "couverte" if statut == "OK" else "hors_corpus"
        if mesure.get("reference_exacte"):
            type_ = "reference_exacte"  # passe la porte par la référence, quel que soit le cosinus
        lignes.append((c["id"], type_, mesure.get("cosinus_max") or 0.0))
    lignes.sort(key=lambda ligne: -ligne[2])
    for id_, type_, cosinus in lignes:
        print(f"{id_:<28} {type_:<17} {cosinus:.3f}")
    couvertes = [cos for _, t, cos in lignes if t == "couverte"]
    hors = [cos for _, t, cos in lignes if t == "hors_corpus"]
    if couvertes and hors and min(couvertes) > max(hors):
        print(f"✔ RAG_SEUIL entre {max(hors):.3f} et {min(couvertes):.3f}")
    else:
        print("✘ aucun seuil ne sépare les questions couvertes des hors corpus (verrous ② ③)")


LIMITE = (
    "Jeux d'évaluation de cette PR rejoués contre staging (code de `main`). "
    "Un prompt modifié ici n'est évalué qu'après merge, par le job `evals`."
)


def _court(bloc: dict[str, Any] | None, cle: str) -> str:
    """12 premiers caractères d'un sha256 du manifeste (bloc absent : questions, corpus)."""
    return ((bloc or {}).get(cle) or "—")[:12]


def resumer(rapport: dict[str, Any], portes_ok: tuple[bool, bool]) -> str:
    """Résumé Markdown du rapport, posté en commentaire de PR (ni jeton ni réponses)."""
    m = rapport["manifeste"]
    seuil, p95_max = m["portes"]["seuil"], m["portes"]["latence_p95_max_s"]
    ratés = [r for r in rapport["resultats"] if r["echecs"]]
    lignes = [
        f"### Évaluations — {'✔ porte passée' if all(portes_ok) else '✘ porte échouée'}",
        "",
        f"- {'✔' if portes_ok[0] else '✘'} réussite {rapport['taux']:.0%} (seuil {seuil:.0%})",
        f"- {'✔' if portes_ok[1] else '✘'} latence p95 {rapport['latence_p95_s']} s"
        f" (max {p95_max} s)",
        "",
    ]
    if ratés:
        lignes += ["| cas | contrôles ratés | http |", "|---|---|---|"]
        lignes += [f"| {r['id']} | {', '.join(r['echecs'])} | {r['http']} |" for r in ratés]
    else:
        lignes.append("Tous les cas passent (aucun cas raté).")
    rejoues = [r for r in rapport["resultats"] if r.get("rejeu")]
    if rejoues:
        detail = ", ".join(
            f"{r['id']} ({r['rejeu']['raison']}, {r['rejeu']['latence_s']} s)" for r in rejoues
        )
        lignes += ["", f"Rejoués une fois : {detail}."]
    if rapport["ecartes"]:
        lignes += ["", f"Cas écartés : {', '.join(rapport['ecartes'])}."]
    lignes += [
        "",
        f"- Cible : {m['cible']} · commit `{m['commit']}`",
        f"- sha256 : golden `{_court(m['golden'], 'sha256')}`, "
        f"questions `{_court(m['questions'], 'sha256')}`, "
        f"corpus `{_court(m['corpus'], 'instantane_sha256')}`",
        f"- Modèle épinglé `{m['modele']['deploiement']}`, observé "
        f"`{', '.join(m['modele']['observe']) or '—'}`",
        f"- Run : {m['run'] or '—'}",
        "",
        f"> {LIMITE}",
    ]
    return "\n".join(lignes) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--golden", type=Path, default=Path("eval/golden.jsonl"))
    parser.add_argument("--questions", type=Path, help="jeu de démo YAML, lu en plus du golden")
    parser.add_argument("--calibrer", action="store_true", help="cosinus max par question")
    # ponytail: seuil de départ, 🔴 à calibrer sur plusieurs runs (comme la couverture, P4)
    parser.add_argument("--seuil", type=float, default=0.8)
    # latence de l'évaluation p95 ≤ 30 s (dossier-conception-v1.md, D11)
    parser.add_argument("--latence-p95-max", type=float, default=30.0)
    parser.add_argument("--prompts", type=Path, default=Path("rag/agentinsurflow_rag/prompts"))
    parser.add_argument("--llm-env", type=Path, default=Path("rag/llm.env"))
    parser.add_argument("--rapport", type=Path)
    parser.add_argument("--resume", type=Path, help="résumé Markdown (commentaire de PR)")
    # ponytail: tant qu'underwriting-admin n'existe pas (U2), un cas à numero_contrat répond 503 ;
    # retirer l'option de la CI quand U2 est déployé
    parser.add_argument(
        "--sans-dossiers", action="store_true", help="écarter les cas à numero_contrat"
    )
    args = parser.parse_args(argv)
    jeton = os.environ.get("EVALS_JETON")  # rôle Gestionnaire ; jamais écrit dans le rapport
    tous = lire_cas(args.golden, args.questions)
    ecartes = [c["id"] for c in tous if args.sans_dossiers and c.get("numero_contrat")]
    tous = [c for c in tous if c["id"] not in ecartes]

    if args.calibrer:
        calibrer(args.url, tous, jeton)
        return 0

    resultats = []
    for cas in tous:
        # un seul rejeu : 429 de la gateway (après la fenêtre), délai client dépassé ou réponse
        # au-dessus de la porte (aléa isolé du LLM, #192) ; la porte juge la réponse rejouée
        rejeu = None
        for essai in range(2):
            debut = time.perf_counter()
            try:
                http, reponse = interroger(args.url, cas, jeton)
            except (OSError, ValueError) as exc:  # réseau, délai client, JSON illisible
                http, reponse = 0, {"erreur": repr(exc)}
            latence = round(time.perf_counter() - debut, 2)  # attente exclue
            raison = (
                "429"
                if http == 429
                else "http 0"
                if http == 0
                else "latence"
                if latence > args.latence_p95_max
                else None
            )
            if raison is None or essai:
                break
            rejeu = {"raison": raison, "latence_s": latence}
            if http == 429:
                time.sleep(ATTENTE_429_S)
        resultats.append(
            {
                "id": cas["id"],
                "echecs": verifier(cas, reponse, http),
                "http": http,
                "latence_s": latence,
                "reponse": reponse,
                **({"rejeu": rejeu} if rejeu else {}),
            }
        )

    taux = sum(not r["echecs"] for r in resultats) / len(resultats)
    latence_p95 = p95([r["latence_s"] for r in resultats])
    portes = {"seuil": args.seuil, "latence_p95_max_s": args.latence_p95_max}
    entete = manifeste(args.url, args.golden, args.prompts, args.llm_env, portes, args.questions)
    # le modèle réellement servi par l'API, pour le comparer au modèle épinglé
    entete["modele"]["observe"] = sorted(
        {str(r["reponse"]["modele"]) for r in resultats if r["reponse"].get("modele")}
    )
    rapport = {
        "manifeste": entete,
        "taux": taux,
        "latence_p95_s": latence_p95,
        "ecartes": ecartes,
        "resultats": resultats,
    }
    sortie = json.dumps(rapport, ensure_ascii=False, indent=2)
    print(sortie)
    if args.rapport:
        args.rapport.write_text(sortie, encoding="utf-8")
    qualite, rapidite = taux >= args.seuil, latence_p95 <= args.latence_p95_max
    if args.resume:
        args.resume.write_text(resumer(rapport, (qualite, rapidite)), encoding="utf-8")
    print(f"{'✔' if qualite else '✘'} réussite {taux:.0%} (seuil {args.seuil:.0%})")
    print(f"{'✔' if rapidite else '✘'} latence p95 {latence_p95} s (max {args.latence_p95_max} s)")
    return 0 if qualite and rapidite else 1


if __name__ == "__main__":
    sys.exit(main())
