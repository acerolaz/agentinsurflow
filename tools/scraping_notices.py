"""Scraping des notices produits publiées par la gateway (``make scraper URL=…``).

Collecte ``<url>/notices/`` (page d'index, puis chaque notice) et écrit un instantané
``notices-<date>.json`` au même format que ``code-assurances-<date>.json`` : manifeste
(date, environnement, périmètre, nombre, SHA-256) et articles, rejouables par ``ingest``.

Courtoisie : ``robots.txt`` est lu et respecté, le User-Agent s'identifie, un délai sépare
deux requêtes. Les six parties du traitement sont visibles : point de lancement (``main``),
initialisation (``initialiser``), règles de traitement (``collecter``, ``extraire_notice``),
gestion des erreurs (``ErreurScraping`` et ``main``), fin de traitement (résumé affiché),
sauvegarde (``sauvegarder_instantane``, écriture atomique).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Sequence
from datetime import date as Date
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import httpx

from agentinsurflow_rag.cli.ingest import sauvegarder_instantane

AGENT = "AgentInsurFlow-scraping/1.0 (+https://github.com/acerolaz/agentinsurflow)"
NOTICES_REQUISES = ("tiers", "tiers_etendu", "tous_risques")
DELAI_S = 1.0
METAS = ("doc_id", "version", "article", "date_debut")
PREFIXES = {"h1": "# ", "h2": "## ", "li": "- ", "p": ""}


class ErreurScraping(Exception):
    """Collecte impossible ou page non conforme : aucun instantané n'est écrit."""


class _Index(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "a" and "notice" in (a.get("class") or "").split() and a.get("href"):
            self.hrefs.append(a["href"] or "")


class _Notice(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.metas: dict[str, str] = {}
        self.lignes: list[str] = []
        self._balise: str | None = None
        self._texte: list[str] = []
        self._dans_main = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "meta" and a.get("name") in METAS:
            self.metas[a["name"] or ""] = (a.get("content") or "").strip()
        elif tag == "main":
            self._dans_main = True
        elif self._dans_main and tag in PREFIXES:
            self._balise, self._texte = tag, []

    def handle_data(self, data: str) -> None:
        if self._balise:
            self._texte.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "main":
            self._dans_main = False
        elif tag == self._balise:
            texte = " ".join("".join(self._texte).split())
            if tag in ("h1", "h2"):
                self.lignes.append("")  # ligne vide avant chaque titre
            self.lignes.append(PREFIXES[tag] + texte)
            self._balise = None


def liens_notices(html: str, base: str) -> list[str]:
    """URL absolues des ``a.notice`` de l'index, dans l'ordre."""
    analyseur = _Index()
    analyseur.feed(html)
    return [urljoin(base, href) for href in analyseur.hrefs]


def extraire_notice(html: str, url: str) -> dict[str, Any]:
    """Un article au format de ``lire_markdown`` ; ``ErreurScraping`` si une méta manque."""
    analyseur = _Notice()
    analyseur.feed(html)
    manquantes = [m for m in METAS if not analyseur.metas.get(m)]
    if manquantes:
        raise ErreurScraping(f"{url} : méta manquante ou vide ({', '.join(manquantes)})")
    return {
        **{m: analyseur.metas[m] for m in METAS},
        "regle_id": None,
        "etat": "VIGUEUR",
        "texte_html": "\n".join(analyseur.lignes).strip(),
        "url_source": url,
    }


def initialiser(client: httpx.Client, base: str) -> RobotFileParser:
    """Lit ``robots.txt`` à la racine du site."""
    url = urljoin(base, "/robots.txt")
    reponse = client.get(url)
    if reponse.status_code != 200:
        raise ErreurScraping(f"{url} : statut {reponse.status_code}")
    robots = RobotFileParser()
    robots.parse(reponse.text.splitlines())
    return robots


def _lire(client: httpx.Client, robots: RobotFileParser, url: str, delai_s: float) -> str:
    if not robots.can_fetch(AGENT, url):
        raise ErreurScraping(f"{url} : interdit par robots.txt")
    time.sleep(delai_s)
    reponse = client.get(url)
    if reponse.status_code != 200:
        raise ErreurScraping(f"{url} : statut {reponse.status_code}")
    return reponse.text


def collecter(client: httpx.Client, base: str, delai_s: float = DELAI_S) -> list[dict[str, Any]]:
    """robots.txt, puis l'index, puis chaque notice ; articles triés par ``doc_id``."""
    robots = initialiser(client, base)
    liens = liens_notices(_lire(client, robots, base, delai_s), base)
    articles = [extraire_notice(_lire(client, robots, u, delai_s), u) for u in liens]
    absentes = [d for d in NOTICES_REQUISES if d not in {a["doc_id"] for a in articles}]
    if absentes:
        raise ErreurScraping(f"notice(s) requise(s) absente(s) : {', '.join(absentes)}")
    return sorted(articles, key=lambda a: str(a["doc_id"]))


def main(
    argv: Sequence[str] | None = None,
    client: httpx.Client | None = None,
    delai_s: float = DELAI_S,
) -> int:
    parseur = argparse.ArgumentParser(description=__doc__)
    parseur.add_argument(
        "--url", required=True, help="racine de la gateway, ex. http://localhost:8000"
    )
    parseur.add_argument("--sortie", type=Path, default=Path("data/raw"))
    parseur.add_argument("--date", default=Date.today().isoformat())
    parseur.add_argument("--environnement", default=os.environ.get("APP_ENV", "local"))
    args = parseur.parse_args(argv)
    base = args.url.rstrip("/") + "/notices/"
    try:
        with client or httpx.Client(headers={"User-Agent": AGENT}, timeout=10.0) as ouvert:
            articles = collecter(ouvert, base, delai_s)
    except (ErreurScraping, httpx.HTTPError) as erreur:
        print(f"✘ scraping interrompu : {erreur}", file=sys.stderr)
        return 1
    chemin = sauvegarder_instantane(
        articles,
        args.sortie,
        args.environnement,
        args.date,
        prefixe="notices",
        perimetre="notices_produits",
    )
    print(f"✔ instantané {chemin} ({len(articles)} notices)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
