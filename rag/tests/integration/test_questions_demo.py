"""Intégration — le jeu de démo ``eval/questions-demo.jsonl`` (spec L10) : rejeu des questions
déterministes (``ci: true`` : références exactes, refus hors corpus, BOLA) sur l'instantané réel
``data/raw/``, avec des modèles simulés.

Les questions qui demandent les vrais modèles sont rejouées en staging par ``tools/evals.py``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
import pytest

from agentinsurflow_rag.domain.reponse import ABSTENTION
from conftest import entetes
from test_reponses_api import brancher
from tools import evals

RACINE = Path(__file__).resolve().parents[3]
QUESTIONS = evals.lire_cas(RACINE / "eval" / "questions-demo.jsonl")
INSTANTANES = sorted((RACINE / "data" / "raw").glob("code-assurances-*.json"))


def test_questions_demo_identifiants_uniques_et_attendus_connus() -> None:
    # une clé inconnue dans « attendu » serait ignorée sans bruit par evals.verifier
    assert len({c["id"] for c in QUESTIONS}) == len(QUESTIONS)
    assert all(set(c["attendu"]) <= {"statut", "articles", "http"} for c in QUESTIONS)


class LLMQuiCiteLePremierExtrait:
    """Modèle simulé : cite le premier extrait du contexte, ou s'abstient s'il n'y en a pas."""

    modele = "fake"

    def completer(self, systeme: str, question: str) -> str:
        premier = re.search(r"^\[([^\]]+)\]", question, re.MULTILINE)
        return f"Selon l'article [{premier.group(1)}], oui." if premier else ABSTENTION


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
    # underwriting-admin simulé : tout contrat demandé appartient à un autre gestionnaire (BOLA)
    brancher(LLMQuiCiteLePremierExtrait(), lambda requete: httpx.Response(404))  # type: ignore[arg-type]

    echecs = {}
    for cas in (c for c in QUESTIONS if c["ci"]):
        corps = {"texte": cas["question"], "numero_contrat": cas.get("numero_contrat")}
        reponse = await api.post("/api/reponses", json=corps, headers=entetes("Gestionnaire"))
        if raisons := evals.verifier(cas, reponse.json(), reponse.status_code):
            echecs[cas["id"]] = raisons
    assert echecs == {}
