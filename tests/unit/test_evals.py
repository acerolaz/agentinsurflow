"""Unitaires — les contrôles des évaluations et la porte (seuil), sans réseau."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tools import evals

OK = {"texte": "Je vous assiste en assurance auto.", "mode": "llm", "modele": "chat"}
CORPUS_REEL = evals.corpus  # la vraie fonction, avant la doublure autouse ci-dessous


@pytest.fixture(autouse=True)
def _sans_reseau(monkeypatch: pytest.MonkeyPatch) -> None:
    """``/health`` simulé : le manifeste lit l'état du corpus de l'API évaluée."""
    monkeypatch.setattr(evals, "corpus", lambda url: {"instantane_sha256": "f" * 64, "chunks": 4})


@pytest.mark.parametrize(
    ("sante", "attendu"),
    [
        # derrière la gateway : /health est celui de la gateway, le corpus est dans /health/rag
        ({"/health/rag": (200, {"corpus": {"chunks": 110}}), "/health": (200, {})}, 110),
        # rag en direct (make run) : pas de /health/rag
        ({"/health/rag": (404, {}), "/health": (200, {"corpus": {"chunks": 4}})}, 4),
    ],
)
def test_le_corpus_vient_de_rag(
    monkeypatch: pytest.MonkeyPatch, sante: dict[str, tuple[int, dict[str, Any]]], attendu: int
) -> None:
    monkeypatch.setattr(evals, "_appeler", lambda url, chemin, jeton: sante[chemin])
    assert CORPUS_REEL("https://x") == {"chunks": attendu}


def test_reponse_conforme() -> None:
    assert evals.verifier({}, OK) == []


@pytest.mark.parametrize(
    ("cas", "reponse", "echecs"),
    [
        ({}, {**OK, "mode": "degrade"}, ["mode_llm"]),
        ({}, {**OK, "texte": " "}, ["non_vide"]),
        ({}, {**OK, "texte": "x" * 601}, ["longueur"]),  # trois phrases au plus
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
        "\n".join(json.dumps({"id": i, "question": q}) for i, q in enumerate(["a", "b"])),
        encoding="utf-8",
    )
    reponses = iter([OK, {**OK, "mode": "degrade"}])
    monkeypatch.setattr(evals, "interroger", lambda url, cas, jeton: (200, next(reponses)))
    rapport = tmp_path / "rapport.json"

    assert evals.main(["--golden", str(golden), "--seuil", "0.8", "--rapport", str(rapport)]) == 1
    assert json.loads(rapport.read_text(encoding="utf-8"))["taux"] == 0.5


def test_p95_rang_le_plus_proche() -> None:
    assert evals.p95([1.0, 5.0, 2.0, 4.0, 3.0]) == 5.0
    assert evals.p95([float(i) for i in range(1, 21)]) == 19.0


def test_la_porte_bloque_si_trop_lent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    golden = tmp_path / "golden.jsonl"
    golden.write_text(json.dumps({"id": "a", "question": "q"}), encoding="utf-8")
    monkeypatch.setattr(evals, "interroger", lambda url, cas, jeton: (200, OK))

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
    monkeypatch.setattr(evals, "interroger", lambda url, cas, jeton: (200, OK))
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


# ---------------------------------------------------------------- contrat RAG (Task R8)

CITEE = {**OK, "statut": "OK", "citations": [{"article": "L211-1"}, {"table": "vue"}]}
REFUS = {"texte": "NOT_FOUND_IN_CORPUS", "mode": "refus", "statut": "NOT_FOUND_IN_CORPUS"}


@pytest.mark.parametrize(
    ("attendu", "reponse", "http", "echecs"),
    [
        ({"statut": "OK", "articles": ["L. 211-1"]}, CITEE, 200, []),
        ({"statut": "OK", "articles": ["A121-1"]}, CITEE, 200, ["articles"]),
        ({"statut": "OK"}, REFUS, 200, ["mode_llm", "statut"]),
        ({"statut": "NOT_FOUND_IN_CORPUS"}, REFUS, 200, []),  # un refus n'a pas à joindre le LLM
        ({"http": 404}, {"code": "CONTRAT_INTROUVABLE"}, 404, []),  # BOLA
        ({"http": 404}, CITEE, 200, ["http"]),
        ({"statut": "OK"}, {"code": "DOSSIERS_INDISPONIBLES"}, 503, ["http"]),
    ],
)
def test_verifier_statut_articles_http(
    attendu: dict[str, Any], reponse: dict[str, Any], http: int, echecs: list[str]
) -> None:
    assert evals.verifier({"attendu": attendu}, reponse, http) == echecs


def _questions(tmp_path: Path) -> Path:
    questions = tmp_path / "questions.jsonl"
    questions.write_text(
        "\n".join(
            json.dumps(cas)
            for cas in [
                {
                    "id": "couverte",
                    "question": "Assurance obligatoire ?",
                    "attendu": {"statut": "OK"},
                },
                {
                    "id": "bola",
                    "question": "Bonus ?",
                    "numero_contrat": "A-1",
                    "attendu": {"http": 404},
                },
            ]
        ),
        encoding="utf-8",
    )
    return questions


def test_questions_lues_en_plus_du_golden_avec_le_jeton(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    golden = tmp_path / "golden.jsonl"
    golden.write_text(json.dumps({"id": "g", "question": "q"}) + "\n", encoding="utf-8")
    recus: list[tuple[str, str | None]] = []

    def interroger(url: str, cas: dict[str, Any], jeton: str | None) -> tuple[int, dict[str, Any]]:
        recus.append((cas["id"], jeton))
        return (404, {}) if cas.get("numero_contrat") else (200, CITEE)

    monkeypatch.setattr(evals, "interroger", interroger)
    monkeypatch.setenv("EVALS_JETON", "jeton-evals")
    rapport = tmp_path / "rapport.json"
    argv = ["--golden", str(golden), "--questions", str(_questions(tmp_path))]

    assert evals.main([*argv, "--rapport", str(rapport)]) == 0
    assert recus == [("g", "jeton-evals"), ("couverte", "jeton-evals"), ("bola", "jeton-evals")]
    m = json.loads(rapport.read_text(encoding="utf-8"))["manifeste"]
    assert m["questions"]["cas"] == ["couverte", "bola"] and len(m["questions"]["sha256"]) == 64
    assert m["corpus"] == {"instantane_sha256": "f" * 64, "chunks": 4}


def test_calibrer_trie_par_cosinus_et_propose_un_seuil(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    golden = tmp_path / "golden.jsonl"
    golden.write_text(
        "\n".join(
            json.dumps({"id": i, "question": q, "attendu": {"statut": s}})
            for i, q, s in [
                ("hors", "points de permis", "NOT_FOUND_IN_CORPUS"),
                ("rc", "assurance obligatoire", "OK"),
                ("ref", "article L211-1", "OK"),
                ("bm", "bonus malus", "OK"),
            ]
        ),
        encoding="utf-8",
    )
    mesures = {
        "points de permis": (0.31, False),
        "assurance obligatoire": (0.72, False),
        "article L211-1": (0.12, True),  # passe la porte par référence exacte : hors calcul
        "bonus malus": (0.55, False),
    }
    monkeypatch.setattr(
        evals,
        "extraits",
        lambda url, question, jeton: dict(
            zip(("cosinus_max", "reference_exacte"), mesures[question], strict=True)
        ),
    )

    assert evals.main(["--golden", str(golden), "--calibrer"]) == 0
    sortie = capsys.readouterr().out
    assert [ligne.split()[0] for ligne in sortie.splitlines()[:4]] == ["rc", "bm", "hors", "ref"]
    assert "RAG_SEUIL entre 0.310 et 0.550" in sortie


def test_un_429_est_rejoue_apres_la_fenetre_hors_latence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    golden = tmp_path / "golden.jsonl"
    golden.write_text(json.dumps({"id": "a", "question": "q"}), encoding="utf-8")
    reponses = iter([(429, {"code": "TROP_DE_REQUETES"}), (200, OK)])
    monkeypatch.setattr(evals, "interroger", lambda url, cas, jeton: next(reponses))
    attentes: list[float] = []
    monkeypatch.setattr(evals.time, "sleep", attentes.append)
    rapport = tmp_path / "rapport.json"

    assert evals.main(["--golden", str(golden), "--rapport", str(rapport)]) == 0
    assert attentes == [evals.ATTENTE_429_S]
    (resultat,) = json.loads(rapport.read_text(encoding="utf-8"))["resultats"]
    assert (resultat["http"], resultat["echecs"]) == (200, [])
    assert resultat["latence_s"] < evals.ATTENTE_429_S  # l'attente n'est pas de la latence


def test_sans_dossiers_ecarte_les_cas_a_numero_de_contrat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    golden = tmp_path / "golden.jsonl"
    golden.write_text(
        "\n".join(
            json.dumps(c)
            for c in [
                {"id": "corpus", "question": "q"},
                {"id": "dossier", "question": "q", "numero_contrat": "A-1"},
            ]
        ),
        encoding="utf-8",
    )
    interroges: list[str] = []

    def interroger(url: str, cas: dict[str, Any], jeton: str | None) -> tuple[int, dict[str, Any]]:
        interroges.append(cas["id"])
        return 200, OK

    monkeypatch.setattr(evals, "interroger", interroger)
    rapport = tmp_path / "rapport.json"

    assert evals.main(["--golden", str(golden), "--sans-dossiers", "--rapport", str(rapport)]) == 0
    assert interroges == ["corpus"]
    assert json.loads(rapport.read_text(encoding="utf-8"))["ecartes"] == ["dossier"]
