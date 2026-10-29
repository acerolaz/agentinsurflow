"""Intégration — la CLI d'ingestion de bout en bout : fichiers (instantané, preuve) sur disque,
PISTE et API simulés (httpx.MockTransport), traces vers un hôte injoignable.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest

from agentinsurflow_rag.cli import ingest
from agentinsurflow_rag.cli.ingest import (
    ErreurEnvoi,
    lire_instantane,
    lire_markdown,
    sauvegarder_instantane,
    sha_articles,
)
from corpus_de_test import CORPUS

PISTE = "sandbox-oauth.piste.gouv.fr"


def _rapport(lot: list[Any], n: int) -> dict[str, Any]:
    return {"id": n, "lus": len(lot), "inseres": len(lot), "inchanges": 0,
            "nouvelles_versions": 0, "rejets": [], "quasi_doublons": [],
            "duree_s": 0.1}  # fmt: skip


@pytest.fixture
def appels(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    """Toutes les requêtes HTTP de la CLI passent par un transport simulé (PISTE et API)."""
    recu: list[httpx.Request] = []

    def repondre(requete: httpx.Request) -> httpx.Response:
        recu.append(requete)
        if requete.url.host == PISTE:
            return httpx.Response(401)
        lot = json.loads(requete.content)["articles"]
        return httpx.Response(201, json=_rapport(lot, len(recu)))

    monkeypatch.setattr(
        ingest, "nouveau_client", lambda: httpx.Client(transport=httpx.MockTransport(repondre))
    )
    monkeypatch.setenv("INGESTION_JETON", "jeton-ingestion")
    monkeypatch.delenv("UNDERWRITING_API_CLIENT_ID", raising=False)
    monkeypatch.delenv("TELEMETRIE_JETON", raising=False)
    return recu


def test_instantane_ecrit_de_facon_atomique(tmp_path: Path) -> None:
    chemin = sauvegarder_instantane(CORPUS, tmp_path / "raw", "local", "2026-10-19")
    assert chemin.name == "code-assurances-2026-10-19.json"
    assert list((tmp_path / "raw").glob("*.tmp")) == []
    contenu = json.loads(chemin.read_text(encoding="utf-8"))
    assert contenu["manifeste"]["sha256"] == sha_articles(contenu["articles"])
    assert contenu["manifeste"]["articles"] == 4


def test_instantane_altere_refuse(tmp_path: Path) -> None:
    chemin = sauvegarder_instantane(CORPUS, tmp_path, "local", "2026-10-19")
    contenu = json.loads(chemin.read_text(encoding="utf-8"))
    contenu["articles"][0]["texte_html"] = "<p>modifié à la main</p>"
    chemin.write_text(json.dumps(contenu), encoding="utf-8")
    with pytest.raises(ErreurEnvoi, match="altéré"):
        lire_instantane(chemin)


def test_lire_instantane_rend_la_date_du_manifeste(tmp_path: Path) -> None:
    chemin = sauvegarder_instantane(CORPUS, tmp_path, "local", "2026-10-19")
    articles, sha, jour = lire_instantane(chemin)
    assert (len(articles), sha, jour) == (4, sha_articles(articles), date(2026, 10, 19))


def test_rejeu_instantane_n_appelle_pas_piste(tmp_path: Path, appels: list[httpx.Request]) -> None:
    chemin = sauvegarder_instantane(CORPUS, tmp_path, "local", "2026-10-19")
    code = ingest.main(
        ["--instantane", str(chemin), "--url", "http://gw", "--preuves", str(tmp_path / "preuves"),
         "--date", "2026-10-19"]
    )  # fmt: skip
    assert code == 0
    assert [r.url.host for r in appels] == ["gw"]
    assert appels[0].headers["authorization"] == "Bearer jeton-ingestion"
    preuve = json.loads((tmp_path / "preuves" / "ingestion-2026-10-19-local.json").read_text())
    assert (preuve["inseres"], preuve["mode"]) == (4, "instantane")
    assert preuve["instantane_date"] == "2026-10-19"
    assert json.loads(appels[0].content)["instantane_date"] == "2026-10-19"


def test_401_piste_code_de_sortie_1(
    tmp_path: Path, appels: list[httpx.Request], monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:  # fmt: skip
    monkeypatch.setenv("LEGIFRANCE_CLIENT_ID", "id")
    monkeypatch.setenv("LEGIFRANCE_CLIENT_SECRET", "faux")
    assert ingest.main(["--dossier", str(tmp_path), "--sans-envoi"]) == 1
    assert "identifiants PISTE invalides" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []  # aucun instantané partiel


def test_sans_identifiants_piste_message_clair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("LEGIFRANCE_CLIENT_ID", raising=False)
    monkeypatch.delenv("LEGIFRANCE_CLIENT_SECRET", raising=False)
    monkeypatch.chdir(tmp_path)  # aucun .env lu
    assert ingest.main(["--sans-envoi"]) == 1
    assert "LEGIFRANCE_CLIENT_ID" in capsys.readouterr().err


def test_echec_export_traces_n_echoue_pas_l_ingestion(
    tmp_path: Path, appels: list[httpx.Request], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TELEMETRIE_JETON", "jeton-telemetrie")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_TIMEOUT", "1")
    chemin = sauvegarder_instantane(CORPUS, tmp_path, "local", "2026-10-19")
    # /v1/traces vise un hôte injoignable (l'exportateur OTLP n'utilise pas httpx)
    code = ingest.main(
        ["--instantane", str(chemin), "--url", "http://hote-injoignable.invalid",
         "--preuves", str(tmp_path)]
    )  # fmt: skip
    assert code == 0


def test_date_du_manifeste_malformee_message_clair(
    tmp_path: Path, appels: list[httpx.Request], capsys: pytest.CaptureFixture[str]
) -> None:
    chemin = sauvegarder_instantane(CORPUS, tmp_path, "local", "pas-une-date")
    assert ingest.main(["--instantane", str(chemin), "--preuves", str(tmp_path)]) == 1
    assert "Invalid isoformat string" in capsys.readouterr().err
    assert appels == []


def test_option_date_malformee_message_clair(
    appels: list[httpx.Request], capsys: pytest.CaptureFixture[str]
) -> None:
    assert ingest.main(["--date", "20/10/2026", "--sans-envoi"]) == 1
    assert "Invalid isoformat string" in capsys.readouterr().err
    assert appels == []


# ---------------------------------------------------------------- documents rédigés (#98)


def _md(
    dossier: Path, nom: str, en_tete: str, corps: str = "Corps du document, assez long."
) -> None:
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / nom).write_text(f"---\n{en_tete}\n---\n{corps}\n", encoding="utf-8")


def _procedure(regle_id: str) -> str:
    en_tete = f"doc_id: PI-{regle_id}\nversion: v1\narticle: PI-{regle_id}\ndate_debut: 2026-10-26"
    return f"{en_tete}\nregle_id: {regle_id}"


TIERS = "doc_id: tiers\nversion: tiers-v1\narticle: NP-TIERS\ndate_debut: 2026-10-26"


def test_lire_markdown_en_tete_et_corps(tmp_path: Path) -> None:
    _md(tmp_path, "tiers.md", TIERS, "# Formule tiers\n\nLa responsabilité civile est couverte.")
    [notice] = lire_markdown(tmp_path, "notices_produits")
    assert (notice["doc_id"], notice["version"], notice["article"]) == (
        "tiers",
        "tiers-v1",
        "NP-TIERS",
    )
    assert (notice["etat"], notice["date_debut"], notice["regle_id"]) == (
        "VIGUEUR",
        "2026-10-26",
        None,
    )
    assert notice["url_source"] == (
        "https://github.com/acerolaz/agentinsurflow/blob/main/rag/corpus/notices_produits/tiers.md"
    )
    assert "La responsabilité civile est couverte." in notice["texte_html"]
    assert "doc_id:" not in notice["texte_html"]


def test_lire_markdown_regle_id_et_ordre(tmp_path: Path) -> None:
    _md(
        tmp_path,
        "R02.md",
        _procedure("R02_RESILIATIONS"),
    )
    _md(
        tmp_path,
        "R01.md",
        _procedure("R01_SUSPENSION"),
    )
    assert [a["regle_id"] for a in lire_markdown(tmp_path, "procedures_internes")] == [
        "R01_SUSPENSION",
        "R02_RESILIATIONS",
    ]


@pytest.mark.parametrize("contenu", ["Pas d'en-tête du tout.", "---\nversion: v1\n---\ncorps"])
def test_markdown_invalide_erreur_qui_nomme_le_fichier(tmp_path: Path, contenu: str) -> None:
    (tmp_path / "casse.md").write_text(contenu, encoding="utf-8")
    with pytest.raises(ErreurEnvoi, match="casse.md"):
        lire_markdown(tmp_path, "notices_produits")


@pytest.mark.parametrize("sous_dossier", ["vide", "inexistant"])
def test_dossier_sans_markdown_echoue(tmp_path: Path, sous_dossier: str) -> None:
    # un SOURCE mal saisi dans deploy.yml ne doit pas passer pour « 0 inséré »
    (tmp_path / "vide").mkdir()
    with pytest.raises(ErreurEnvoi, match=sous_dossier):
        lire_markdown(tmp_path / sous_dossier, "notices_produits")


def test_procedure_sans_regle_id_refusee(tmp_path: Path) -> None:
    # sans regle_id, GF5 échouerait en silence sur chaque refus fondé sur cette procédure
    _md(tmp_path, "R01.md", "doc_id: PI-R01\nversion: v1\narticle: PI-R01\ndate_debut: 2026-10-26")
    with pytest.raises(ErreurEnvoi, match="R01.md.*regle_id"):
        lire_markdown(tmp_path, "procedures_internes")


def test_source_envoie_la_collection_et_ecrit_sa_preuve(
    tmp_path: Path, appels: list[httpx.Request]
) -> None:
    _md(tmp_path / "src", "tiers.md", TIERS)
    code = ingest.main(
        ["--collection", "notices_produits", "--source", str(tmp_path / "src"), "--url", "http://gw",
         "--preuves", str(tmp_path / "preuves"), "--date", "2026-10-26", "--environnement", "local"]
    )  # fmt: skip
    assert code == 0
    corps = json.loads(appels[0].content)
    assert corps["collection"] == "notices_produits" and corps["articles"][0]["doc_id"] == "tiers"
    preuve = json.loads(
        (tmp_path / "preuves" / "ingestion-notices_produits-2026-10-26-local.json").read_text()
    )
    assert preuve["mode"] == "markdown"


@pytest.mark.parametrize(
    "arguments",
    [["--source", "x"], ["--collection", "notices_produits"]],
)
def test_collection_et_source_vont_ensemble(
    arguments: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert ingest.main(arguments) == 1
    assert "--source" in capsys.readouterr().err


# ---------------------------------------------------------------- jeu agrégé (#52)


def _jeu(chemin: Path) -> Path:
    entrees = [
        {**CORPUS[0], "collection": c, "source": "x", "doc_id": f"d-{c}"}
        for c in ingest.COLLECTIONS
    ]
    manifeste = {"date": "2026-10-27", "entrees": 3, "sha256": sha_articles(entrees)}
    chemin.write_text(json.dumps({"manifeste": manifeste, "entrees": entrees}), encoding="utf-8")
    return chemin


def test_jeu_envoie_chaque_collection_et_ecrit_ses_preuves(
    tmp_path: Path, appels: list[httpx.Request]
) -> None:
    code = ingest.main(
        ["--jeu", str(_jeu(tmp_path / "jeu.json")), "--url", "http://gw",
         "--preuves", str(tmp_path / "preuves"), "--environnement", "local"]
    )  # fmt: skip
    assert code == 0
    corps = [json.loads(r.content) for r in appels]
    assert [c["collection"] for c in corps] == list(ingest.COLLECTIONS)
    assert all("source" not in a and "collection" not in a for c in corps for a in c["articles"])
    assert sorted(p.name for p in (tmp_path / "preuves").iterdir()) == [
        "ingestion-2026-10-27-local.json",
        "ingestion-notices_produits-2026-10-27-local.json",
        "ingestion-procedures_internes-2026-10-27-local.json",
    ]
    preuve = json.loads((tmp_path / "preuves" / "ingestion-2026-10-27-local.json").read_text())
    assert preuve["mode"] == "jeu"


def test_jeu_altere_refuse(
    tmp_path: Path, appels: list[httpx.Request], capsys: pytest.CaptureFixture[str]
) -> None:
    chemin = _jeu(tmp_path / "jeu.json")
    contenu = json.loads(chemin.read_text())
    contenu["entrees"][0]["texte_html"] = "modifié"
    chemin.write_text(json.dumps(contenu), encoding="utf-8")
    assert ingest.main(["--jeu", str(chemin), "--preuves", str(tmp_path)]) == 1
    assert "altéré" in capsys.readouterr().err
    assert appels == []


@pytest.mark.parametrize(
    "autres",
    [["--instantane", "x"], ["--collection", "notices_produits", "--source", "x"]],
)
def test_jeu_exclusif_avec_instantane_et_source(
    tmp_path: Path, appels: list[httpx.Request], autres: list[str]
) -> None:
    assert ingest.main(["--jeu", str(_jeu(tmp_path / "jeu.json")), *autres]) == 1
    assert appels == []


def test_procedures_par_source_refusees(
    tmp_path: Path, appels: list[httpx.Request], capsys: pytest.CaptureFixture[str]
) -> None:
    _md(tmp_path / "src", "R01.md", _procedure("R01_SUSPENSION"))
    code = ingest.main(["--collection", "procedures_internes", "--source", str(tmp_path / "src")])
    assert code == 1
    assert "make agreger" in capsys.readouterr().err
    assert appels == []


def test_jeu_sans_une_collection_refuse(
    tmp_path: Path, appels: list[httpx.Request], capsys: pytest.CaptureFixture[str]
) -> None:
    chemin = _jeu(tmp_path / "jeu.json")
    contenu = json.loads(chemin.read_text())
    contenu["entrees"] = contenu["entrees"][:2]
    contenu["manifeste"]["sha256"] = sha_articles(contenu["entrees"])
    chemin.write_text(json.dumps(contenu), encoding="utf-8")
    assert ingest.main(["--jeu", str(chemin), "--preuves", str(tmp_path)]) == 1
    assert "jeu sans entrée pour procedures_internes" in capsys.readouterr().err
    assert appels == []


def test_instantane_vide_ecrit_une_preuve_a_zero(
    tmp_path: Path, appels: list[httpx.Request]
) -> None:
    chemin = sauvegarder_instantane([], tmp_path, "local", "2026-10-19")
    code = ingest.main(
        ["--instantane", str(chemin), "--preuves", str(tmp_path / "p"), "--date", "2026-10-19"]
    )
    assert code == 0
    assert (
        json.loads((tmp_path / "p" / "ingestion-2026-10-19-local.json").read_text())["inseres"] == 0
    )
def _instantane_notices(tmp_path: Path) -> Path:
    return sauvegarder_instantane(
        CORPUS, tmp_path, "local", "2026-10-29", prefixe="notices", perimetre="notices_produits"
    )


def test_instantane_prefixe_et_perimetre(tmp_path: Path) -> None:
    chemin = _instantane_notices(tmp_path)
    assert chemin.name == "notices-2026-10-29.json"
    assert json.loads(chemin.read_text(encoding="utf-8"))["manifeste"]["perimetre"] == (
        "notices_produits"
    )


def test_rejeu_instantane_notices_dans_sa_collection(
    tmp_path: Path, appels: list[httpx.Request]
) -> None:
    chemin = _instantane_notices(tmp_path)
    code = ingest.main(
        ["--instantane", str(chemin), "--collection", "notices_produits", "--url", "http://gw",
         "--preuves", str(tmp_path / "preuves"), "--date", "2026-10-29"]
    )  # fmt: skip
    assert code == 0
    assert json.loads(appels[0].content)["collection"] == "notices_produits"


def test_instantane_notices_refuse_dans_une_autre_collection(
    tmp_path: Path, appels: list[httpx.Request], capsys: pytest.CaptureFixture[str]
) -> None:
    chemin = _instantane_notices(tmp_path)
    code = ingest.main(["--instantane", str(chemin), "--url", "http://gw"])
    assert code == 1
    assert "notices_produits" in capsys.readouterr().err
    assert appels == []


def test_instantane_legifrance_refuse_dans_une_collection_de_notices(
    tmp_path: Path, appels: list[httpx.Request], capsys: pytest.CaptureFixture[str]
) -> None:
    chemin = sauvegarder_instantane(
        CORPUS, tmp_path, "local", "2026-10-29", perimetre="LEGIARTI0000.*"
    )
    code = ingest.main(
        ["--instantane", str(chemin), "--collection", "notices_produits", "--url", "http://gw"]
    )
    assert code == 1
    assert "textes_reglementaires" in capsys.readouterr().err
    assert appels == []


def test_source_et_instantane_exclusifs(
    tmp_path: Path, appels: list[httpx.Request], capsys: pytest.CaptureFixture[str]
) -> None:
    chemin = _instantane_notices(tmp_path)
    code = ingest.main(
        ["--instantane", str(chemin), "--source", str(tmp_path), "--collection", "notices_produits"]
    )
    assert code == 1
    assert "--source" in capsys.readouterr().err
