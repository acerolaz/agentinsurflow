"""Unitaires — configuration des connexions de rag à ``vecteurs`` (aucune connexion ouverte)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlalchemy.engine import make_url

from agentinsurflow_rag.infrastructure.postgres.connexions import ConfigBD


def _config(**valeurs: str) -> ConfigBD:
    defaut = {"pg_writer_password": "mdp-writer", "pg_reader_password": "mdp-reader"}
    return ConfigBD(_env_file=None, **{**defaut, **valeurs})  # type: ignore[arg-type]


def test_url_contient_base_suffixee_et_pilote_async() -> None:
    url = _config(pg_suffixe_bases="_test").url("reader")
    assert url.startswith("postgresql+asyncpg://reader:")
    assert url.endswith("@localhost:5432/vecteurs_test")


def test_chaque_compte_a_son_mot_de_passe() -> None:
    cfg = _config()
    assert make_url(cfg.url("writer")).password == "mdp-writer"
    assert make_url(cfg.url("reader")).password == "mdp-reader"


def test_mot_de_passe_a_caracteres_speciaux_encode() -> None:
    url = make_url(_config(pg_writer_password="p@ss:/w#rd").url("writer"))
    assert (url.password, url.host, url.database) == ("p@ss:/w#rd", "localhost", "vecteurs")


def test_migrateur_facultatif_pour_les_routes_mais_exige_pour_migrer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PG_MIGRATEUR_PASSWORD", raising=False)
    cfg = _config()  # l'API démarre sans le mot de passe du propriétaire
    with pytest.raises(ValueError, match="PG_MIGRATEUR_PASSWORD"):
        cfg.url("migrateur")
    assert make_url(_config(pg_migrateur_password="m").url("migrateur")).username == "migrateur"


def test_mots_de_passe_obligatoires(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PG_WRITER_PASSWORD", raising=False)
    monkeypatch.delenv("PG_READER_PASSWORD", raising=False)
    with pytest.raises(ValidationError):
        ConfigBD(_env_file=None)  # type: ignore[call-arg]
