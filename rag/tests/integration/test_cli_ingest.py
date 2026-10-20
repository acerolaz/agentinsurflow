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
