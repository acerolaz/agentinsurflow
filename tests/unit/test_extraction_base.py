"""TU — ``tools/extraction_base.py`` : connexion simulée, aucune base (C1)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tools import extraction_base as eb

LIGNES = [{"formule": "tiers", "tranche_age": "25-34", "nb_dossiers": 2, "crm_moyen": 0.9,
           "sinistres_moyens": 0.5, "avec_releve": 2}]  # fmt: skip


class Connexion:
    def __init__(self, lignes: list[dict[str, Any]]) -> None:
        self.lignes = lignes
        self.ferme = False

    async def fetch(self, _sql: str) -> list[dict[str, Any]]:
        return self.lignes

    async def close(self) -> None:
        self.ferme = True


def _main(tmp_path: Path, connexion: Any, *args: str) -> int:
    async def connecter(**_options: Any) -> Any:
        if isinstance(connexion, Exception):
            raise connexion
        return connexion

    return eb.main(["--sortie", str(tmp_path), "--date", "2026-11-02", *args], connecter)


@pytest.mark.parametrize(
    "colonne", ["numero_contrat", "gestionnaire_id", "observations", "departement"]
)
def test_la_requete_ne_lit_aucune_donnee_identifiante(colonne: str) -> None:
    assert colonne not in eb.REQUETE


def test_la_requete_lit_la_vue_minimisee_et_jamais_une_table() -> None:
    assert "FROM vue_contrat_minimisee" in eb.REQUETE
    assert "souscripteur" not in eb.REQUETE


def test_instantane_ecrit_et_connexion_fermee(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PG_DOSSIERS_PASSWORD", "x")
    connexion = Connexion(LIGNES)
    assert _main(tmp_path, connexion) == 0
    contenu = json.loads((tmp_path / "dossiers-agregats-2026-11-02.json").read_text("utf-8"))
    assert contenu["articles"] == LIGNES
    assert contenu["manifeste"]["perimetre"] == "vue_contrat_minimisee"
    assert connexion.ferme


def test_sans_mot_de_passe_message_clair_sans_connexion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("PG_DOSSIERS_PASSWORD", raising=False)
    assert _main(tmp_path, AssertionError("aucune connexion attendue")) == 1
    assert "PG_DOSSIERS_PASSWORD" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_base_injoignable_code_1_sans_instantane_ni_mot_de_passe_affiche(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PG_DOSSIERS_PASSWORD", "secret-a-ne-pas-afficher")
    assert _main(tmp_path, OSError("connexion refusée")) == 1
    erreur = capsys.readouterr().err
    assert "connexion refusée" in erreur and "secret-a-ne-pas-afficher" not in erreur
    assert list(tmp_path.iterdir()) == []


def test_base_vide_refusee_sans_instantane(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PG_DOSSIERS_PASSWORD", "x")
    connexion = Connexion([])
    assert _main(tmp_path, connexion) == 1
    assert "aucun dossier" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == [] and connexion.ferme


def test_app_env_vide_vaut_local(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PG_DOSSIERS_PASSWORD", "x")
    monkeypatch.setenv("APP_ENV", "")
    assert _main(tmp_path, Connexion(LIGNES)) == 0
    contenu = json.loads((tmp_path / "dossiers-agregats-2026-11-02.json").read_text("utf-8"))
    assert contenu["manifeste"]["environnement"] == "local"
