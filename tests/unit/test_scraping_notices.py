"""Unitaires — le scraping des notices produits, sans réseau : un ``MockTransport`` sert
``/robots.txt`` et les vraies pages de ``gateway/.../wwwroot/notices/``."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from agentinsurflow_rag.cli.ingest import sha_articles
from tools import scraping_notices as sn

NOTICES = (
    Path(__file__).resolve().parents[2] / "gateway/src/AgentInsurFlow.Gateway.Api/wwwroot/notices"
)
ROBOTS_OK = "User-agent: *\nAllow: /notices/\nDisallow: /\n"
ROBOTS_KO = "User-agent: *\nDisallow: /\n"
BASE = "http://gw/notices/"


def _client(
    robots: str = ROBOTS_OK, pages: dict[str, str] | None = None, agents: list[str] | None = None
) -> httpx.Client:
    def repondre(requete: httpx.Request) -> httpx.Response:
        if agents is not None:
            agents.append(requete.headers["user-agent"])
        chemin = requete.url.path
        if chemin == "/robots.txt":
            return httpx.Response(200, text=robots)
        nom = chemin.removeprefix("/notices/") or "index.html"
        if pages is not None and nom in pages:
            return httpx.Response(200, text=pages[nom])
        fichier = NOTICES / nom
        if fichier.is_file():
            return httpx.Response(200, text=fichier.read_text(encoding="utf-8"))
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(repondre), headers={"User-Agent": sn.AGENT})


def _lire(nom: str) -> str:
    return (NOTICES / nom).read_text(encoding="utf-8")


def test_extraire_notice_tiers() -> None:
    article = sn.extraire_notice(_lire("tiers.html"), BASE + "tiers.html")
    assert article["doc_id"] == "tiers"
    assert article["version"] == "tiers-2026.10-v1"
    assert article["article"] == "NP-TIERS"
    assert article["regle_id"] is None
    assert article["etat"] == "VIGUEUR"
    assert "## Garanties" in article["texte_html"]
    assert "- Responsabilité civile" in article["texte_html"]


def test_liens_index() -> None:
    liens = sn.liens_notices(_lire("index.html"), BASE)
    assert len(liens) == 4
    assert BASE + "tiers.html" in liens


def test_collecter_les_trois_formules() -> None:
    agents: list[str] = []
    articles = sn.collecter(_client(agents=agents), BASE, delai_s=0)
    ids = [a["doc_id"] for a in articles]
    assert set(sn.NOTICES_REQUISES) <= set(ids)
    assert ids == sorted(ids)
    assert all(a["url_source"].startswith(BASE) for a in articles)
    assert set(agents) == {sn.AGENT}


def test_robots_interdit_notices(tmp_path: Path) -> None:
    with pytest.raises(sn.ErreurScraping):
        sn.collecter(_client(robots=ROBOTS_KO), BASE, delai_s=0)
    code = sn.main(["--url", "http://gw", "--sortie", str(tmp_path)], client=_client(ROBOTS_KO))
    assert code == 1
    assert list(tmp_path.iterdir()) == []


def test_notice_sans_doc_id(tmp_path: Path) -> None:
    page = _lire("tiers.html").replace('<meta name="doc_id" content="tiers">', "")
    with pytest.raises(sn.ErreurScraping, match="tiers.html"):
        sn.collecter(_client(pages={"tiers.html": page}), BASE, delai_s=0)


def test_formule_manquante() -> None:
    index = "\n".join(
        ligne for ligne in _lire("index.html").splitlines() if "tous_risques" not in ligne
    )
    with pytest.raises(sn.ErreurScraping, match="tous_risques"):
        sn.collecter(_client(pages={"index.html": index}), BASE, delai_s=0)


def test_main_ecrit_instantane_et_manifeste(tmp_path: Path) -> None:
    code = sn.main(
        ["--url", "http://gw", "--sortie", str(tmp_path), "--date", "2026-10-29"],
        client=_client(),
    )
    assert code == 0
    contenu = json.loads((tmp_path / "notices-2026-10-29.json").read_text(encoding="utf-8"))
    assert contenu["manifeste"]["articles"] == 4
    assert contenu["manifeste"]["perimetre"] == "notices_produits"
    assert contenu["manifeste"]["sha256"] == sha_articles(contenu["articles"])
