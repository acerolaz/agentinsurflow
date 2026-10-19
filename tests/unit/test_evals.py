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


def test_p95_rang_le_plus_proche() -> None:
    assert evals.p95([1.0, 5.0, 2.0, 4.0, 3.0]) == 5.0
    assert evals.p95([float(i) for i in range(1, 21)]) == 19.0


def test_la_porte_bloque_si_trop_lent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    golden = tmp_path / "golden.jsonl"
    golden.write_text(json.dumps({"id": "a", "question": "q"}), encoding="utf-8")
    monkeypatch.setattr(evals, "interroger", lambda url, question: OK)

    assert evals.main(["--golden", str(golden)]) == 0
    assert evals.main(["--golden", str(golden), "--latence-p95-max", "-1"]) == 1


def test_le_rapport_s_ouvre_sur_le_manifeste(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    golden = tmp_path / "golden.jsonl"
    golden.write_text(json.dumps({"id": "domaine", "question": "q"}) + "\n", encoding="utf-8")
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "systeme.md").write_text("Tu es l'assistant.", encoding="utf-8")
    llm_env = tmp_path / "llm.env"
    llm_env.write_text("# épinglé\nAZURE_OPENAI_DEPLOYMENT=Kimi-K2.5\n", encoding="utf-8")
    monkeypatch.setattr(evals, "interroger", lambda url, question: OK)
    monkeypatch.setenv("GITHUB_SHA", "abc123")
    monkeypatch.setenv("GITHUB_RUN_NUMBER", "42")
    rapport = tmp_path / "rapport.json"

    code = evals.main(
        [
            "--golden",
            str(golden),
            "--prompts",
            str(prompts),
            "--llm-env",
            str(llm_env),
            "--rapport",
            str(rapport),
        ]
    )

    m = json.loads(rapport.read_text(encoding="utf-8"))["manifeste"]
    assert code == 0 and m["commit"] == "abc123" and m["version"].endswith("-build.42")
    assert m["modele"] == {"fichier": str(llm_env), "deploiement": "Kimi-K2.5", "observe": ["chat"]}
    assert m["prompts"][0]["contenu"] == "Tu es l'assistant."
    assert len(m["prompts"][0]["sha256"]) == 64
    assert m["golden"]["cas"] == ["domaine"] and len(m["golden"]["sha256"]) == 64
    assert m["portes"] == {"seuil": 0.8, "latence_p95_max_s": 30.0}


@pytest.mark.parametrize(("run", "attendu"), [("42", "1.2.3-build.42"), (None, "1.2.3-local")])
def test_version_manifeste(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, run: str | None, attendu: str
) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nversion = "1.2.3"\n', encoding="utf-8")
    if run:
        monkeypatch.setenv("GITHUB_RUN_NUMBER", run)
    else:
        monkeypatch.delenv("GITHUB_RUN_NUMBER", raising=False)
    assert evals.version_manifeste(pyproject) == attendu
