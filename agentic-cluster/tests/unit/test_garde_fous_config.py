"""TU — la configuration des garde-fous refuse une liste de sujets vide (avant tout modèle)."""

import pytest

from agentinsurflow_cluster.infrastructure.garde_fous.llm_guard import (
    ConfigGardeFous,
    ScannersLlmGuard,
)


def test_sujets_vides_leve_une_erreur_explicite() -> None:
    with pytest.raises(ValueError, match="sujets_hors_perimetre"):
        ScannersLlmGuard(ConfigGardeFous(_env_file=None, sujets_hors_perimetre=""))
