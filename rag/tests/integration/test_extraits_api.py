"""Intégration — recherche hybride (``/api/extraits``) et traçabilité (``/api/documents``) sur
PostgreSQL : SQL RRF réel, porte de pertinence, références exactes, versions obsolètes.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from agentinsurflow_rag.api import app
from agentinsurflow_rag.api.dependances import ConfigRag, charger_rag, connexion_reader
from agentinsurflow_rag.infrastructure.postgres.connexions import ConfigBD, creer_moteurs
from conftest import entetes
from corpus_de_test import CORPUS, SHA

GESTIONNAIRE = entetes("Gestionnaire")


async def _extraits(api: httpx.AsyncClient, question: str, **parametres: Any) -> dict[str, Any]:
    reponse = await api.get(
        "/api/extraits", params={"question": question, **parametres}, headers=GESTIONNAIRE
    )
    assert reponse.status_code == 200, reponse.text
    resultat: dict[str, Any] = reponse.json()
    return resultat


async def test_question_couverte_cite_l_article(corpus: httpx.AsyncClient) -> None:
    resultat = await _extraits(corpus, "coefficient bonus malus appliqué à la prime")
    assert resultat["statut"] == "OK"
    premier = resultat["resultats"][0]
    assert premier["citation"]["article"] == "A121-1"
    assert premier["citation"]["url_source"].startswith("https://www.legifrance.gouv.fr/")
    assert premier["cosinus"] >= 0.4


async def test_question_hors_corpus_refusee(corpus: httpx.AsyncClient) -> None:
    resultat = await _extraits(corpus, "recette de la tarte aux pommes")
    assert (resultat["statut"], resultat["resultats"]) == ("NOT_FOUND_IN_CORPUS", [])


async def test_reference_exacte_passe_meme_sous_le_seuil(corpus: httpx.AsyncClient) -> None:
    app.dependency_overrides[charger_rag] = lambda: ConfigRag(_env_file=None, rag_seuil=0.99)  # type: ignore[call-arg]
    resultat = await _extraits(corpus, "Que dit l'article L. 211-2 ?")
    assert resultat["statut"] == "OK" and resultat["reference_exacte"]
    assert resultat["resultats"][0]["citation"]["article"] == "L211-2"


async def test_plein_texte_seul_retrouve_un_numero(corpus: httpx.AsyncClient) -> None:
    # « franchise » n'est que dans R211-45 : le classement plein texte (GIN) le remonte
    resultat = await _extraits(corpus, "franchise à la charge de l'assuré victimes")
    assert resultat["resultats"][0]["citation"]["article"] == "R211-45"


async def test_version_obsolete_exclue(corpus: httpx.AsyncClient) -> None:
    modifie = CORPUS[2] | {
        "version": "v2",
        "texte_html": "<p>Nouvelle rédaction de la clause de réduction majoration.</p>",
    }
    corps = {"collection": "textes_reglementaires", "instantane_sha256": SHA, "articles": [modifie]}
    await corpus.post("/api/ingestions", json=corps, headers=entetes("Ingestion"))
    resultat = await _extraits(corpus, "A121-1")
    textes = [e["texte"] for e in resultat["resultats"] if e["citation"]["article"] == "A121-1"]
    assert textes == ["Nouvelle rédaction de la clause de réduction majoration."]


async def test_question_sans_mot_refusee(corpus: httpx.AsyncClient) -> None:
    assert (await _extraits(corpus, "???"))["statut"] == "NOT_FOUND_IN_CORPUS"


async def test_base_vide_refus_propre(api: httpx.AsyncClient) -> None:
    resultat = await _extraits(api, "assurance obligatoire du véhicule")
    assert (resultat["statut"], resultat["cosinus_max"]) == ("NOT_FOUND_IN_CORPUS", None)


async def test_top_k_respecte(corpus: httpx.AsyncClient) -> None:
    app.dependency_overrides[charger_rag] = lambda: ConfigRag(_env_file=None, rag_seuil=0.0)  # type: ignore[call-arg]
    assert len((await _extraits(corpus, "assurance véhicule", top_k=2))["resultats"]) == 2


@pytest.mark.parametrize("parametres", [{"question": ""}, {"question": "x", "top_k": 21}, {}])
async def test_requete_invalide_422(api: httpx.AsyncClient, parametres: dict[str, Any]) -> None:
    reponse = await api.get("/api/extraits", params=parametres, headers=GESTIONNAIRE)
    assert reponse.status_code == 422


async def test_recherche_exige_le_role_gestionnaire(api: httpx.AsyncClient) -> None:
    reponse = await api.get(
        "/api/extraits", params={"question": "L211-1"}, headers=entetes("Ingestion")
    )
    assert reponse.status_code == 403


async def test_recherche_et_documents_utilisent_le_compte_reader(
    api: httpx.AsyncClient, conn_writer: AsyncConnection
) -> None:
    appels: list[str] = []

    async def _reader() -> AsyncIterator[AsyncConnection]:
        appels.append("reader")
        yield conn_writer

    app.dependency_overrides[connexion_reader] = _reader
    await api.get("/api/extraits", params={"question": "L211-1"}, headers=GESTIONNAIRE)
    await api.get("/api/documents/LEGIARTI000006800836", headers=GESTIONNAIRE)
    assert appels == ["reader", "reader"]


async def test_document_trace_versions_et_chunks(corpus: httpx.AsyncClient) -> None:
    reponse = await corpus.get("/api/documents/LEGIARTI000006800836", headers=GESTIONNAIRE)
    assert reponse.status_code == 200
    document = reponse.json()
    assert document["collection"] == "textes_reglementaires"
    assert [v["version"] for v in document["versions"]] == ["LEGIARTI000006800836-v1"]
    assert document["chunks"][0]["article"] == "L211-1"
    assert "embedding" not in document["chunks"][0]


async def test_document_inconnu_404(api: httpx.AsyncClient) -> None:
    reponse = await api.get("/api/documents/LEGIARTI_INCONNU", headers=GESTIONNAIRE)
    assert reponse.status_code == 404
    assert reponse.json()["code"] == "DOCUMENT_INTROUVABLE"


async def test_base_injoignable_503_problem_details(api: httpx.AsyncClient) -> None:
    del app.dependency_overrides[connexion_reader]  # le vrai câblage, vers un port fermé
    app.state.moteurs = creer_moteurs(
        ConfigBD(_env_file=None, pg_port=1, pg_writer_password="x", pg_reader_password="x")  # type: ignore[call-arg, arg-type]
    )
    try:
        reponse = await api.get(
            "/api/extraits", params={"question": "bonus malus"}, headers=GESTIONNAIRE
        )
    finally:
        await app.state.moteurs.fermer()
        app.state.moteurs = None
    assert reponse.status_code == 503
    assert reponse.headers["content-type"] == "application/problem+json"
    assert reponse.json()["code"] == "BASE_INDISPONIBLE"
