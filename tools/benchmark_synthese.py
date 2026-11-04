#!/usr/bin/env python3
"""Benchmark C7 : prix officiels, puis mesures du RAG et des agents → ``benchmark.md``.

``--prix <sortie.json>`` relève l'API publique Azure Retail Prices.
``--dossier <preuves>`` lit ``prix.json``, ``rag-*.json``, ``agents.json`` ; écrit ``benchmark.md``.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from tools.evals import p95

SEUIL_TAUX = 0.8
AGENTS = ("pieces", "analyste", "redacteur", "actuaire")
_MODELES = {
    "gpt-4.1-mini": re.compile(r"gpt 4\.1 mini", re.I),
    "gpt-5-mini": re.compile(r"gpt 5 mini", re.I),
    "Kimi-K2.5": re.compile(r"kimi.?k2\.5", re.I),
}
_EXCLUS = re.compile(r"cach|cchd|\bcd\b|\bch\b|batch|ptu|training|\bft\b|regnl", re.I)
_URL_PRIX = "https://prices.azure.com/api/retail/prices?api-version=2023-01-01-preview&$filter="
_FILTRE_PRIX = "serviceName eq 'Foundry Models' and armRegionName eq 'swedencentral'"

Prix = Mapping[str, Mapping[str, Mapping[str, float]]]


def _type_deploiement(nom: str) -> str | None:
    if re.search(r"\b(glbl|gl|global)\b", nom, re.I):
        return "global"
    if re.search(r"\b(dz|dzone|data zone)\b", nom, re.I):
        return "data_zone"
    return None


def _sens(nom: str) -> str | None:
    if re.search(r"\binp", nom, re.I):
        return "entree"
    if re.search(r"\boutp", nom, re.I):
        return "sortie"
    return None


def parser_prix(items: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, float]]]:
    """Modèle → ``global``/``data_zone`` → ``entree``/``sortie``, en USD par million de tokens."""
    prix: dict[str, dict[str, dict[str, float]]] = {}
    for item in items:
        nom = str(item["meterName"])
        modele = next((m for m, motif in _MODELES.items() if motif.search(nom)), None)
        deploiement, sens = _type_deploiement(nom), _sens(nom)
        if modele is None or deploiement is None or sens is None or _EXCLUS.search(nom):
            continue
        par_million = float(item["retailPrice"]) * (1000 if item["unitOfMeasure"] == "1K" else 1)
        prix.setdefault(modele, {}).setdefault(deploiement, {})[sens] = round(par_million, 6)
    return prix


def prix_retenu(prix: Prix, modele: str) -> tuple[dict[str, float], str]:
    """Le prix du type déployé (Global) ; à défaut, Data Zone, annoncé comme référence."""
    types = prix[modele]
    cle = "global" if "global" in types else "data_zone"
    return dict(types[cle]), cle


def cout_usd(entree: int, sortie: int, prix: Mapping[str, float]) -> float:
    return (entree * prix["entree"] + sortie * prix["sortie"]) / 1_000_000


def charger_rag(chemin: Path, modele: str) -> dict[str, Any]:
    """Un rapport de ``tools/evals.py`` ; refusé s'il n'a pas interrogé le modèle annoncé."""
    rapport = json.loads(chemin.read_text(encoding="utf-8"))
    observe = rapport["manifeste"]["modele"]["observe"]
    if observe != [modele]:
        raise ValueError(f"{chemin.name} : modèle observé {observe}, attendu {modele}")
    return {
        "modele": modele,
        "taux": rapport["taux"],
        "latence_p95_s": rapport["latence_p95_s"],
        "resultats": len(rapport["resultats"]),
    }


def _bilan_agent(mesures: list[dict[str, Any]]) -> dict[str, Any]:
    reussies = [m for m in mesures if m["statut"] == "ok"]
    latences = [float(m["latence_s"]) for m in reussies]
    return {
        "essais": len(mesures),
        "ok": len(reussies),
        "p50_s": statistics.median(latences) if latences else None,
        "p95_s": p95(latences) if latences else None,
        "tokens_entree": statistics.mean(m["tokens_entree"] for m in reussies)
        if reussies
        else None,
        "tokens_sortie": statistics.mean(m["tokens_sortie"] for m in reussies)
        if reussies
        else None,
        "causes": dict(Counter(m["cause"] for m in mesures if m["statut"] != "ok")),
    }


def synthese_agents(mesures: list[dict[str, Any]], prix: Prix) -> dict[str, dict[str, Any]]:
    """Par modèle : bilan par agent et coût par dossier (somme des coûts moyens des agents)."""
    synthese: dict[str, dict[str, Any]] = {}
    for modele in sorted({m["modele"] for m in mesures}):
        agents = {
            agent: _bilan_agent(
                [m for m in mesures if m["modele"] == modele and m["agent"] == agent]
            )
            for agent in AGENTS
        }
        tarif, reference = prix_retenu(prix, modele)
        couts = [
            cout_usd(a["tokens_entree"], a["tokens_sortie"], tarif) if a["ok"] else None
            for a in agents.values()
        ]
        cout = None if None in couts else sum(c for c in couts if c is not None)
        synthese[modele] = {"agents": agents, "cout_dossier_usd": cout, "reference_prix": reference}
    return synthese


def verdict(taux: float | None, structure_ok: bool, outil_ok: bool, deployable: bool) -> str:
    """Critères bloquants fixés avant les mesures (spec §6.2)."""
    ok = taux is not None and taux >= SEUIL_TAUX and structure_ok and outil_ok and deployable
    return "répond" if ok else "ne répond pas"


def _nombre(valeur: float | None, format_: str = ".2f") -> str:
    return "—" if valeur is None else format(valeur, format_)


def _verdict_modele(modele: str, rag: list[dict[str, Any]], agents: Mapping[str, Any]) -> str:
    taux = next((r["taux"] for r in rag if r["modele"] == modele), None)
    bilan = agents.get(modele, {}).get("agents", {})
    structure = bool(bilan) and all(a["ok"] > 0 for a in bilan.values())
    outil = bool(bilan) and bilan["redacteur"]["ok"] > 0
    return verdict(taux, structure, outil, True)


def tableaux_markdown(rag: list[dict[str, Any]], agents: Mapping[str, Any]) -> str:
    lignes = ["## Usage RAG", "", "| Modèle | Taux | Latence p95 (s) | Cas |", "|---|---|---|---|"]
    lignes += [
        f"| `{r['modele']}` | {r['taux']:.2f} | {r['latence_p95_s']:.2f} | {r['resultats']} |"
        for r in rag
    ]
    lignes += ["", "## Usage agents", ""]
    lignes += [
        "| Modèle | Agent | Réussites | p50 (s) | p95 (s) | Tokens entrée | Tokens sortie "
        "| Échecs |"
    ]
    lignes += ["|---|---|---|---|---|---|---|---|"]
    for modele, bloc in agents.items():
        for nom, a in bloc["agents"].items():
            causes = ", ".join(f"{c} : {n}" for c, n in a["causes"].items()) or "aucun"
            lignes.append(
                f"| `{modele}` | {nom} | {a['ok']}/{a['essais']} | {_nombre(a['p50_s'])} "
                f"| {_nombre(a['p95_s'])} | {_nombre(a['tokens_entree'], '.0f')} "
                f"| {_nombre(a['tokens_sortie'], '.0f')} | {causes} |"
            )
    lignes += ["", "## Coût par dossier et verdict", ""]
    lignes += [
        "Coût approximé : somme des coûts moyens de quatre agents, sur les seules mesures "
        "réussies, hors Saga complète.",
        "",
        "Verdict : taux ≥ 0,8 et au moins une réussite par agent. Le critère « déployable » "
        "n'est pas mesuré ici : il vient de la lecture des déploiements de la ressource.",
        "",
    ]
    lignes += [
        "| Modèle | Coût par dossier (USD) | Verdict sur les critères bloquants |",
        "|---|---|---|",
    ]
    for modele in sorted({*agents, *(r["modele"] for r in rag)}):
        bloc = agents.get(modele, {})
        reference = " (réf. Data Zone)" if bloc.get("reference_prix") == "data_zone" else ""
        lignes.append(
            f"| `{modele}` | {_nombre(bloc.get('cout_dossier_usd'), '.4f')}{reference} "
            f"| {_verdict_modele(modele, rag, agents)} |"
        )
    return "\n".join(lignes) + "\n"


def relever_prix() -> list[dict[str, Any]]:
    url: str | None = _URL_PRIX + urllib.parse.quote(_FILTRE_PRIX)
    items: list[dict[str, Any]] = []
    while url:
        with urllib.request.urlopen(url, timeout=30) as reponse:  # noqa: S310 (URL fixe, https)
            page = json.load(reponse)
        items += page["Items"]
        url = page.get("NextPageLink")
    return items


def ecrire_synthese(dossier: Path) -> Path:
    prix = json.loads((dossier / "prix.json").read_text(encoding="utf-8"))
    rag = [charger_rag(f, f.stem.removeprefix("rag-")) for f in sorted(dossier.glob("rag-*.json"))]
    campagne = json.loads((dossier / "agents.json").read_text(encoding="utf-8"))
    sortie = dossier / "benchmark.md"
    sortie.write_text(
        "# Benchmark des modèles Foundry\n\n"
        + tableaux_markdown(rag, synthese_agents(campagne["mesures"], prix)),
        encoding="utf-8",
    )
    return sortie


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prix", type=Path, help="relève les prix officiels dans ce fichier")
    parser.add_argument(
        "--dossier", type=Path, help="écrit benchmark.md à partir des mesures de ce dossier"
    )
    args = parser.parse_args(argv)
    if args.prix:
        args.prix.parent.mkdir(parents=True, exist_ok=True)
        args.prix.write_text(
            json.dumps(parser_prix(relever_prix()), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"✔ {args.prix}")
    if args.dossier:
        print(f"✔ {ecrire_synthese(args.dossier)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
