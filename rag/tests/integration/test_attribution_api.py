"""Intégration — ``GET /api/documents/{doc_id}/attribution`` (Etalab 2.0) sur PostgreSQL."""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from agentinsurflow_rag.api import app
from conftest import entetes
from corpus_de_test import CORPUS, DATE_ISO

GESTIONNAIRE = entetes("Gestionnaire")
DOC = CORPUS[0]["doc_id"]
URL = f"/api/documents/{DOC}/attribution"


async def test_attribution_200_champs_de_la_spec(corpus: httpx.AsyncClient) -> None:
    r = await corpus.get(URL, headers=GESTIONNAIRE)
    assert r.status_code == 200, r.text
    assert r.json() == {
        "doc_id": DOC,
        "article": "L211-1",
        "version": f"{DOC}-v1",
        "date_debut": "2003-01-01",
        "url_source": CORPUS[0]["url_source"],
        "source": "Légifrance",
        "concedant": "Direction de l'information légale et administrative (DILA)",
        "licence": {
            "nom": "Licence Ouverte / Open Licence version 2.0",
            "url": "https://www.etalab.gouv.fr/licence-ouverte-open-licence/",
        },
        "mise_a_jour_le": DATE_ISO,
        "modifications": (
            "Texte retraité par AgentInsurFlow : balises HTML retirées, texte normalisé et "
            "découpé en extraits. Le texte original est consultable via url_source."
        ),
    }


async def test_attribution_version_explicite(corpus: httpx.AsyncClient) -> None:
    r = await corpus.get(URL, params={"version": f"{DOC}-v1"}, headers=GESTIONNAIRE)
    assert r.status_code == 200 and r.json()["version"] == f"{DOC}-v1"


async def test_attribution_sans_jeton_401(api: httpx.AsyncClient) -> None:
    assert (await api.get(URL)).status_code == 401


async def test_attribution_sans_role_gestionnaire_403(api: httpx.AsyncClient) -> None:
    assert (await api.get(URL, headers=entetes("Ingestion"))).status_code == 403


async def test_article_inconnu_404_document_introuvable(api: httpx.AsyncClient) -> None:
    r = await api.get("/api/documents/LEGIARTI_INCONNU/attribution", headers=GESTIONNAIRE)
    assert (r.status_code, r.json()["code"]) == (404, "DOCUMENT_INTROUVABLE")


async def test_article_hors_collection_404_comme_inconnu(
    corpus: httpx.AsyncClient, conn_writer: AsyncConnection
) -> None:
    await conn_writer.execute(text("UPDATE document SET collection = 'cgv_conditions'"))
    r = await corpus.get(URL, headers=GESTIONNAIRE)
    assert (r.status_code, r.json()["code"]) == (404, "DOCUMENT_INTROUVABLE")


async def test_version_inconnue_404_version_introuvable(corpus: httpx.AsyncClient) -> None:
    r = await corpus.get(URL, params={"version": "v999"}, headers=GESTIONNAIRE)
    assert (r.status_code, r.json()["code"]) == (404, "VERSION_INTROUVABLE")


async def test_version_avec_caracteres_encodes(corpus: httpx.AsyncClient) -> None:
    r = await corpus.get(f"{URL}?version=1.0-%C3%A9", headers=GESTIONNAIRE)
    assert (r.status_code, r.json()["code"]) == (404, "VERSION_INTROUVABLE")


async def test_version_vide_422(corpus: httpx.AsyncClient) -> None:
    assert (await corpus.get(f"{URL}?version=", headers=GESTIONNAIRE)).status_code == 422


def test_route_publiee_dans_l_openapi() -> None:
    chemins = TestClient(app).get("/openapi.json").json()["paths"]
    assert "/api/documents/{doc_id}/attribution" in chemins
