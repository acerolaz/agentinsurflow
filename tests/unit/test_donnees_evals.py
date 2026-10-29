"""Unitaires — le test des données d'évaluation (schéma, articles, sha256), sans réseau.

Niveau : TU (fonctions pures sur des chaînes) ; ``main`` lit des fichiers (``tmp_path``, dépôt) :
TI légers, gardés peu nombreux.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tools.donnees_evals import articles_manquants, controler_cas, dernier_instantane, main


def test_cas_conformes_sans_erreur() -> None:
    ligne = '{"id": "a", "question": "q ?", "attendu": {"statut": "OK", "articles": ["L211-1"]}}'
    assert controler_cas([ligne, ""], "g") == []


@pytest.mark.parametrize(
    ("ligne", "raison"),
    [
        ("pas du json", "JSON"),
        ('{"question": "q"}', "id"),
        ('{"id": "a", "question": ""}', "question"),
        ('{"id": "a", "question": "q", "attendu": {"statuts": "OK"}}', "attendu"),
        ('{"id": "a", "question": "q", "attendu": {"statut": "PEUT-ETRE"}}', "statut"),
        ('{"id": "a", "question": "q", "inconnu": 1}', "inconnu"),
    ],
)
def test_chaque_defaut_de_schema_est_signale(ligne: str, raison: str) -> None:
    erreurs = controler_cas([ligne], "g")
    assert len(erreurs) == 1 and erreurs[0].startswith("g:1 ") and raison in erreurs[0]


def test_id_en_double_signale() -> None:
    ligne = '{"id": "a", "question": "q"}'
    assert any("a" in e and "double" in e for e in controler_cas([ligne, ligne], "g"))


def test_article_absent_de_l_instantane() -> None:
    cas = [{"id": "x", "attendu": {"articles": ["L999-9"]}}]
    assert articles_manquants(cas, {"L211-1"}) == ["x : article L999-9 absent de l'instantané"]


def test_article_normalise_avant_comparaison() -> None:
    cas = [{"id": "x", "attendu": {"articles": ["L. 211-1"]}}]
    assert articles_manquants(cas, {"L211-1"}) == []


def test_dernier_instantane_par_nom(tmp_path: Path) -> None:
    for d in ("2026-10-20", "2026-10-27"):
        (tmp_path / f"code-assurances-{d}.json").write_text("{}")
    assert dernier_instantane(tmp_path).name == "code-assurances-2026-10-27.json"


def test_instantane_altere_echoue(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    manifeste = {"date": "2026-10-27", "articles": 1, "sha256": "0" * 64}
    contenu = {"manifeste": manifeste, "articles": [{"article": "L211-1"}]}
    (tmp_path / "code-assurances-2026-10-27.json").write_text(json.dumps(contenu))
    assert main(["--instantanes", str(tmp_path)]) == 1
    assert "altéré" in capsys.readouterr().out


def test_fichier_absent_signale_sans_trace(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--golden", str(tmp_path / "absent.jsonl")]) == 1
    assert "✘" in capsys.readouterr().out


def test_manifeste_mal_forme_signale_sans_trace(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    articles: list[dict[str, str]] = []
    sha = hashlib.sha256(b"[]").hexdigest()  # JSON canonique de la liste vide
    contenu = {"manifeste": {"date": "2026-10-27", "sha256": sha}, "articles": articles}
    (tmp_path / "code-assurances-2026-10-27.json").write_text(json.dumps(contenu))
    assert main(["--instantanes", str(tmp_path)]) == 1
    assert "✘" in capsys.readouterr().out


def test_depot_actuel_conforme() -> None:
    assert main([]) == 0
