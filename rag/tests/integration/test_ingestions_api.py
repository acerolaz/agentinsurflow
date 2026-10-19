"""Intégration — ressource REST ``/api/ingestions`` contre PostgreSQL (rôle Ingestion)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from agentinsurflow_rag.api import app
from agentinsurflow_rag.api.dependances import obtenir_embeddings
from agentinsurflow_rag.domain.ports import ErreurEmbeddings
from agentinsurflow_rag.infrastructure.postgres.corpus import PgDepotCorpus
from conftest import entetes
from corpus_de_test import CORPUS, SHA
from fakes import FakeEmbeddings

INGESTION = entetes("Ingestion")


def lot(articles: list[dict[str, Any]] | None = None, **autres: Any) -> dict[str, Any]:
    return {
        "collection": "textes_reglementaires",
        "instantane_sha256": SHA,
        "articles": CORPUS if articles is None else articles,
    } | autres


async def _documents(conn: AsyncConnection) -> int:
    return int(await conn.scalar(text("SELECT count(*) FROM document")) or 0)


async def test_post_ingestion_201_location_et_rapport(api: httpx.AsyncClient) -> None:
    reponse = await api.post("/api/ingestions", json=lot(), headers=INGESTION)
    assert reponse.status_code == 201
    rapport = reponse.json()
    assert reponse.headers["location"] == f"/api/ingestions/{rapport['id']}"
    assert (rapport["lus"], rapport["inseres"], rapport["inchanges"]) == (4, 4, 0)


async def test_rejeu_idempotent(api: httpx.AsyncClient, conn_writer: AsyncConnection) -> None:
    await api.post("/api/ingestions", json=lot(), headers=INGESTION)
    second = (await api.post("/api/ingestions", json=lot(), headers=INGESTION)).json()
    assert (second["inseres"], second["inchanges"]) == (0, 4)
    assert await _documents(conn_writer) == 4


async def test_nouvelle_version_rend_l_ancienne_obsolete(
    api: httpx.AsyncClient, conn_writer: AsyncConnection
) -> None:
    await api.post("/api/ingestions", json=lot(CORPUS[:1]), headers=INGESTION)
    modifie = CORPUS[0] | {"version": "v2", "texte_html": "<p>Nouveau texte de l'article.</p>"}
    rapport = (await api.post("/api/ingestions", json=lot([modifie]), headers=INGESTION)).json()
    assert rapport["nouvelles_versions"] == 1
    courantes = await conn_writer.scalar(text("SELECT count(*) FROM document WHERE NOT obsolete"))
    assert (courantes, await _documents(conn_writer)) == (1, 2)


async def test_lot_concurrent_409_sans_deuxieme_version_courante(
    api: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await api.post("/api/ingestions", json=lot(CORPUS[:1]), headers=INGESTION)

    async def aucune(self: PgDepotCorpus, doc_id: str) -> None:
        return None  # l'autre lot a écrit après notre lecture (course entre deux transactions)

    monkeypatch.setattr(PgDepotCorpus, "version_courante", aucune)
    v2 = CORPUS[0] | {"version": "v2", "texte_html": "<p>Autre texte de l'article, assez long.</p>"}
    reponse = await api.post("/api/ingestions", json=lot([v2]), headers=INGESTION)
    assert (reponse.status_code, reponse.json()["code"]) == (409, "CONFLIT_INGESTION")


async def test_article_partiel_rejete_sans_bloquer_le_lot(api: httpx.AsyncClient) -> None:
    sans_texte = {k: v for k, v in CORPUS[2].items() if k != "texte_html"}
    rapport = (
        await api.post("/api/ingestions", json=lot([*CORPUS[:2], sans_texte]), headers=INGESTION)
    ).json()
    assert rapport["inseres"] == 2
    assert rapport["rejets"] == [{"doc_id": CORPUS[2]["doc_id"], "raison": "partiel:texte_html"}]


async def test_quasi_doublon_signale_pas_rejete(api: httpx.AsyncClient) -> None:
    jumeau = CORPUS[0] | {"doc_id": "LEGIARTI_JUMEAU", "version": "j1", "article": "L. 211-1-1"}
    rapport = (
        await api.post("/api/ingestions", json=lot([CORPUS[0], jumeau]), headers=INGESTION)
    ).json()
    assert rapport["inseres"] == 2
    assert [d["proche_de"] for d in rapport["quasi_doublons"]] == [CORPUS[0]["doc_id"]]


@pytest.mark.parametrize(
    "corps",
    [
        lot(collection="procedures_internes"),
        lot(instantane_sha256="pas-un-sha"),
        lot([]),
        lot(CORPUS * 13),  # 52 articles > 50
    ],
)
async def test_lot_invalide_422(api: httpx.AsyncClient, corps: dict[str, Any]) -> None:
    assert (await api.post("/api/ingestions", json=corps, headers=INGESTION)).status_code == 422


async def test_embeddings_en_panne_503_rien_n_est_ecrit(
    api: httpx.AsyncClient, conn_writer: AsyncConnection
) -> None:
    app.dependency_overrides[obtenir_embeddings] = lambda: FakeEmbeddings(
        erreur=ErreurEmbeddings("panne")
    )
    reponse = await api.post("/api/ingestions", json=lot(), headers=INGESTION)
    assert reponse.status_code == 503
    assert reponse.json()["code"] == "EMBEDDINGS_INDISPONIBLES"
    assert await _documents(conn_writer) == 0


async def test_ingestion_exige_le_role_ingestion(api: httpx.AsyncClient) -> None:
    reponse = await api.post("/api/ingestions", json=lot(), headers=entetes("Gestionnaire"))
    assert reponse.status_code == 403
    assert (await api.post("/api/ingestions", json=lot())).status_code == 401


async def test_rapport_journalise_puis_relu(api: httpx.AsyncClient) -> None:
    cree = (await api.post("/api/ingestions", json=lot(), headers=INGESTION)).json()
    lu = await api.get(f"/api/ingestions/{cree['id']}", headers=INGESTION)
    assert lu.status_code == 200
    assert lu.json()["instantane_sha256"] == SHA
    assert lu.json()["rapport"]["inseres"] == 4


async def test_liste_des_ingestions_paginee(api: httpx.AsyncClient) -> None:
    for _ in range(3):
        await api.post("/api/ingestions", json=lot(CORPUS[:1]), headers=INGESTION)
    page = (await api.get("/api/ingestions?limit=2&offset=0", headers=INGESTION)).json()
    suite = (await api.get("/api/ingestions?limit=2&offset=2", headers=INGESTION)).json()
    assert len(page) == 2 and len(suite) == 1
    assert page[0]["id"] > page[1]["id"] > suite[0]["id"]  # du plus récent au plus ancien


async def test_ingestion_inconnue_404(api: httpx.AsyncClient) -> None:
    reponse = await api.get("/api/ingestions/999999", headers=INGESTION)
    assert reponse.status_code == 404
    assert reponse.json()["code"] == "INGESTION_INTROUVABLE"
