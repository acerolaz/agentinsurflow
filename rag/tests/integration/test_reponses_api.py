"""Intégration — ``POST /api/reponses`` de bout en bout dans le processus : recherche sur
PostgreSQL, agent (FakeLLM), underwriting-admin simulé (httpx.MockTransport), OBO simulé,
traces OTel relevées en mémoire.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from agentinsurflow_rag.api import app
from agentinsurflow_rag.api.routes.agent import obtenir_dossiers, obtenir_llm
from agentinsurflow_rag.domain.ports import ErreurDossiers, ErreurLLM
from agentinsurflow_rag.domain.reponse import MESSAGE_REFUS
from agentinsurflow_rag.infrastructure.underwriting.client import ClientUnderwriting
from conftest import entetes
from fakes import FakeLLM

GESTIONNAIRE = entetes("Gestionnaire")
VUE = {
    "numero_contrat": "AIF-2026-0001",
    "tranche_age": "25-34",
    "anciennete_permis_ans": 6,
    "departement": "69",
    "crm_bonus_malus": 0.85,
    "nb_sinistres": 1,
    "suspensions": 0,
    "resiliations": 0,
    "formule": "tous risques",
    "mis_a_jour": "2026-09-01T00:00:00+00:00",
}
QUESTION = "Comment le coefficient bonus malus s'applique-t-il à la prime ?"


async def _obo() -> str:
    return "jeton-obo"


def brancher(
    llm: FakeLLM | None = None,
    underwriting: Callable[[httpx.Request], httpx.Response] | None = None,
    obo: Callable[[], Awaitable[str]] = _obo,
) -> FakeLLM:
    llm = llm or FakeLLM("Le coefficient s'applique à la prime [A121-1].")
    app.dependency_overrides[obtenir_llm] = lambda: llm
    transport = httpx.MockTransport(underwriting or (lambda r: httpx.Response(200, json=VUE)))
    app.dependency_overrides[obtenir_dossiers] = lambda: ClientUnderwriting(
        httpx.AsyncClient(transport=transport), "http://underwriting:8002", obo
    )
    return llm


async def _poser(api: httpx.AsyncClient, **corps: Any) -> httpx.Response:
    return await api.post("/api/reponses", json={"texte": QUESTION} | corps, headers=GESTIONNAIRE)


async def test_sans_jeton_401(api: httpx.AsyncClient) -> None:
    reponse = await api.post("/api/reponses", json={"texte": QUESTION})
    assert (reponse.status_code, reponse.json()["code"]) == (401, "JETON_ABSENT")


async def test_reponses_exige_le_role_gestionnaire(api: httpx.AsyncClient) -> None:
    brancher()
    reponse = await api.post(
        "/api/reponses", json={"texte": QUESTION}, headers=entetes("Ingestion")
    )
    assert reponse.status_code == 403


async def test_question_couverte_bout_en_bout(corpus: httpx.AsyncClient) -> None:
    brancher()
    reponse = await _poser(corpus)
    assert reponse.status_code == 200
    corps = reponse.json()
    assert (corps["statut"], corps["mode"], corps["modele"]) == ("OK", "llm", "fake")
    assert corps["citations"][0]["article"] == "A121-1"
    assert corps["citations"][0]["url_source"].startswith("https://www.legifrance.gouv.fr/")
    assert len(corps["trace_id"]) == 32


async def test_hors_corpus_refus_sans_appel_llm(corpus: httpx.AsyncClient) -> None:
    llm = brancher()
    corps = (await _poser(corpus, texte="recette de la tarte aux pommes")).json()
    assert (corps["statut"], corps["texte"], corps["citations"]) == (
        "NOT_FOUND_IN_CORPUS",
        MESSAGE_REFUS,
        [],
    )
    assert llm.appels == []


async def test_contrat_ajoute_la_citation_sql(corpus: httpx.AsyncClient) -> None:
    llm = brancher()
    corps = (await _poser(corpus, numero_contrat="AIF-2026-0001")).json()
    assert {"table": "vue_contrat_minimisee", "identifiant": "AIF-2026-0001"}.items() <= next(
        c for c in corps["citations"] if "table" in c
    ).items()
    assert "crm_bonus_malus : 0.85" in llm.appels[0][1]


async def test_contrat_d_un_autre_gestionnaire_404(corpus: httpx.AsyncClient) -> None:
    llm = brancher(underwriting=lambda r: httpx.Response(404))
    reponse = await _poser(corpus, numero_contrat="AIF-2026-0099")
    assert (reponse.status_code, reponse.json()["code"]) == (404, "CONTRAT_INTROUVABLE")
    assert llm.appels == []


async def test_obo_refuse_503(corpus: httpx.AsyncClient) -> None:
    async def refuse() -> str:
        raise ErreurDossiers("consentement manquant")

    llm = brancher(obo=refuse)
    reponse = await _poser(corpus, numero_contrat="AIF-2026-0001")
    assert (reponse.status_code, reponse.json()["code"]) == (503, "DOSSIERS_INDISPONIBLES")
    assert llm.appels == []  # l'agent ne répond pas sans la vue


async def test_agent_sans_contrat_ok_si_underwriting_down(corpus: httpx.AsyncClient) -> None:
    def panne(requete: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refusé", request=requete)

    brancher(underwriting=panne)
    assert (await _poser(corpus)).json()["statut"] == "OK"


async def test_appel_underwriting_porte_traceparent_et_jeton_obo(
    corpus: httpx.AsyncClient,
) -> None:
    recu: list[httpx.Request] = []

    def repondre(requete: httpx.Request) -> httpx.Response:
        recu.append(requete)
        return httpx.Response(200, json=VUE)

    brancher(underwriting=repondre)
    corps = (await _poser(corpus, numero_contrat="AIF-2026-0001")).json()
    (requete,) = recu
    assert requete.headers["authorization"] == "Bearer jeton-obo"
    assert requete.headers["traceparent"].split("-")[1] == corps["trace_id"]


async def test_llm_en_panne_revue_humaine(corpus: httpx.AsyncClient) -> None:
    brancher(llm=FakeLLM(erreur=ErreurLLM("délai dépassé")))
    corps = (await _poser(corpus)).json()
    assert (corps["statut"], corps["mode"]) == ("REVUE_HUMAINE", "degrade")
    assert corps["citations"]


@pytest.mark.parametrize("numero", ["../traces", "AIF 2026", "x" * 41])
async def test_numero_contrat_invalide_422(api: httpx.AsyncClient, numero: str) -> None:
    brancher()
    assert (await _poser(api, numero_contrat=numero)).status_code == 422


async def test_spans_exportes_sans_la_question(
    corpus: httpx.AsyncClient, spans: InMemorySpanExporter
) -> None:
    brancher()
    question = "Jean Dupont, 12 rue des Lilas : le bonus malus s'applique-t-il à la prime ?"
    await _poser(corpus, texte=question, numero_contrat="AIF-2026-0001")
    par_nom = {s.name: s for s in spans.get_finished_spans()}
    assert {"POST /api/reponses", "agent.repondre", "rag.recherche"} <= set(par_nom)
    agent = dict(par_nom["agent.repondre"].attributes or {})
    assert agent["question.longueur"] == len(question)
    assert len(str(agent["question.sha256"])) == 64
    assert agent["contrat.present"] is True and "agent.verrou" in agent
    recherche = dict(par_nom["rag.recherche"].attributes or {})
    assert recherche["rag.statut"] == agent["agent.statut"] and "rag.seuil" in recherche
    valeurs = _texte_des_spans(spans)
    assert "Dupont" not in valeurs and "Lilas" not in valeurs and "AIF-2026-0001" not in valeurs


def _texte_des_spans(spans: InMemorySpanExporter) -> str:
    """Tout ce qui part en OTLP : attributs des spans **et** de leurs événements (exceptions)."""
    return " ".join(
        str(v)
        for s in spans.get_finished_spans()
        for attributs in [s.attributes, *(e.attributes for e in s.events)]
        for v in (attributs or {}).values()
    )


async def test_contrat_introuvable_sans_numero_dans_les_traces(
    corpus: httpx.AsyncClient, spans: InMemorySpanExporter
) -> None:
    brancher(underwriting=lambda r: httpx.Response(404))
    assert (await _poser(corpus, numero_contrat="AIF-2026-0099")).status_code == 404
    assert "AIF-2026-0099" not in _texte_des_spans(spans)


async def test_extraits_sans_la_question_dans_les_traces(
    corpus: httpx.AsyncClient, spans: InMemorySpanExporter
) -> None:
    reponse = await corpus.get(
        "/api/extraits", params={"question": "Jean Dupont bonus malus"}, headers=GESTIONNAIRE
    )
    assert reponse.status_code == 200
    assert "Dupont" not in _texte_des_spans(spans)
