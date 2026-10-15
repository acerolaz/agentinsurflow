"""Unitaires — les contrôles des évaluations et la porte (seuil), sans réseau."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tools import evals

OK = {"texte": "Je vous assiste en assurance auto.", "mode": "llm", "modele": "chat"}


def test_reponse_conforme() -> None:
    assert evals.verifier({"contient_un": ["Assurance"]}, OK) == []


@pytest.mark.parametrize(
    ("cas", "reponse", "echecs"),
    [
        ({}, {**OK, "mode": "degrade"}, ["mode_llm"]),
        ({}, {**OK, "texte": " "}, ["non_vide"]),
        ({"max_caracteres": 10}, OK, ["longueur"]),
        ({"contient_un": ["franchise"]}, OK, ["contient_un"]),
        ({}, {"erreur": "HTTP 503"}, ["mode_llm", "non_vide"]),
    ],
)
def test_chaque_controle_rate(
    cas: dict[str, Any], reponse: dict[str, Any], echecs: list[str]
) -> None:
    assert evals.verifier(cas, reponse) == echecs


def test_la_porte_bloque_sous_le_seuil(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    golden = tmp_path / "golden.jsonl"
    golden.write_text(
        "\n".join(
            json.dumps({"id": i, "question": q, "contient_un": ["assurance"]})
            for i, q in enumerate(["a", "b"])
        ),
        encoding="utf-8",
    )
    reponses = iter([OK, {**OK, "texte": "hors sujet"}])
    monkeypatch.setattr(evals, "interroger", lambda url, question: next(reponses))
    rapport = tmp_path / "rapport.json"

    assert evals.main(["--golden", str(golden), "--seuil", "0.8", "--rapport", str(rapport)]) == 1
    assert json.loads(rapport.read_text(encoding="utf-8"))["taux"] == 0.5
