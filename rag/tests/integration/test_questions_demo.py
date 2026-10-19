"""Intégration — le jeu de démo ``eval/questions-demo.yaml`` (spec L10) : structure des fichiers
d'évaluation, et rejeu des questions déterministes (``ci: true`` : références exactes, refus hors
corpus, BOLA) sur l'instantané réel ``data/raw/``, avec des modèles simulés.

Les questions qui demandent les vrais modèles sont rejouées en staging par ``tools/evals.py``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml  # type: ignore[import-untyped]

from agentinsurflow_rag.api import app
from agentinsurflow_rag.api.routes.agent import obtenir_dossiers, obtenir_llm
from agentinsurflow_rag.domain.reponse import ABSTENTION
from agentinsurflow_rag.infrastructure.underwriting.client import ClientUnderwriting
from conftest import entetes
from tools import evals

RACINE = Path(__file__).resolve().parents[3]
QUESTIONS = RACINE / "eval" / "questions-demo.yaml"
GOLDEN = RACINE / "eval" / "golden.jsonl"
INSTANTANES = sorted((RACINE / "data" / "raw").glob("code-assurances-*.json"))


def _questions() -> list[dict[str, Any]]:
    cas: list[dict[str, Any]] = yaml.safe_load(QUESTIONS.read_text(encoding="utf-8"))
    return cas


def test_questions_demo_structure() -> None:
    cas = _questions()
    assert 5 <= len(cas) <= 10
    assert len({c["id"] for c in cas}) == len(cas)
    assert all(set(c["attendu"]) <= {"statut", "articles", "http"} for c in cas)
    assert all(isinstance(c["ci"], bool) and c["question"].strip() for c in cas)
    statuts = [c["attendu"].get("statut") for c in cas]
    assert statuts.count("OK") >= 1 and statuts.count("NOT_FOUND_IN_CORPUS") >= 1
    # chaque question couverte dit quel article elle doit citer
    assert all(c["attendu"].get("articles") for c in cas if c["attendu"].get("statut") == "OK")
    assert any(c.get("numero_contrat") and c["attendu"].get("statut") == "OK" for c in cas)
    assert any(c.get("numero_contrat") and c["attendu"].get("http") == 404 for c in cas)  # BOLA


def test_golden_au_contrat_rag() -> None:
    cas = evals.lire_cas(GOLDEN)
    assert len(cas) == 5
    assert all(c["attendu"].get("statut") in ("OK", "NOT_FOUND_IN_CORPUS") for c in cas)


class LLMQuiCiteLePremierExtrait:
    """Modèle simulé : cite le premier extrait du contexte, ou s'abstient s'il n'y en a pas."""

    modele = "fake"

    def completer(self, systeme: str, question: str) -> str:
        premier = re.search(r"^\[([^\]]+)\]", question, re.MULTILINE)
        return f"Selon l'article [{premier.group(1)}], oui." if premier else ABSTENTION


async def _obo() -> str:
    return "jeton-obo"


@pytest.mark.skipif(
    not INSTANTANES, reason="instantané réel absent de data/raw/ : make extraire (PISTE, G0)"
)
async def test_rejeu_questions_ci_sur_instantane_reel(api: httpx.AsyncClient) -> None:
    contenu = json.loads(INSTANTANES[-1].read_text(encoding="utf-8"))
    articles = contenu["articles"]
    for debut in range(0, len(articles), 50):
        lot = {
            "collection": "textes_reglementaires",
            "instantane_sha256": contenu["manifeste"]["sha256"],
            "articles": articles[debut : debut + 50],
        }
        reponse = await api.post("/api/ingestions", json=lot, headers=entetes("Ingestion"))
        assert reponse.status_code == 201, reponse.text
    app.dependency_overrides[obtenir_llm] = lambda: LLMQuiCiteLePremierExtrait()
    # underwriting-admin simulé : tout contrat demandé appartient à un autre gestionnaire (BOLA)
    transport = httpx.MockTransport(lambda requete: httpx.Response(404))
    app.dependency_overrides[obtenir_dossiers] = lambda: ClientUnderwriting(
        httpx.AsyncClient(transport=transport), "http://underwriting:8002", _obo
    )

    echecs = {}
    for cas in (c for c in _questions() if c["ci"]):
        corps = {"texte": cas["question"]}
        if cas.get("numero_contrat"):
            corps["numero_contrat"] = cas["numero_contrat"]
        reponse = await api.post("/api/reponses", json=corps, headers=entetes("Gestionnaire"))
        if raisons := evals.verifier(cas, reponse.json(), reponse.status_code):
            echecs[cas["id"]] = raisons
    assert echecs == {}
