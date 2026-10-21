"""Unitaires — cas d'usage des outils de lecture, ports simulés seulement."""

from __future__ import annotations

import pytest
from fakes_mcp import FauxCorpus, FauxDossiers, FauxJetons, appelant

from agentinsurflow_mcp.application.outils import get_contrat, search_rag
from agentinsurflow_mcp.domain.models import (
    CONTRAT_INTROUVABLE,
    DOSSIERS_INDISPONIBLES,
    NOT_FOUND_IN_CORPUS,
    ErreurOutil,
)


async def test_search_rag_passe_le_jeton_obo_rag() -> None:
    jetons, corpus = FauxJetons(), FauxCorpus()
    resultat = await search_rag(appelant(), jetons, corpus, "franchise ?", 3)
    assert jetons.demandes == [("jeton-entrant", "rag")]
    assert corpus.appels == [("obo-rag", "franchise ?", 3)]
    assert resultat["statut"] == "OK"


async def test_search_rag_propage_not_found_in_corpus() -> None:
    corpus = FauxCorpus(ErreurOutil(NOT_FOUND_IN_CORPUS, "hors corpus"))
    with pytest.raises(ErreurOutil) as exc:
        await search_rag(appelant(), FauxJetons(), corpus, "recette de crêpes")
    assert exc.value.code == NOT_FOUND_IN_CORPUS


async def test_get_contrat_passe_le_jeton_obo_underwriting() -> None:
    jetons, dossiers = FauxJetons(), FauxDossiers()
    resultat = await get_contrat(appelant("orchestrateur"), jetons, dossiers, "AIF/1")
    assert jetons.demandes == [("jeton-entrant", "underwriting")]
    assert dossiers.appels == [("obo-underwriting", "AIF/1")]
    assert resultat == {"numero_contrat": "AIF/1"}


async def test_get_contrat_introuvable() -> None:
    dossiers = FauxDossiers(ErreurOutil(CONTRAT_INTROUVABLE, "introuvable"))
    with pytest.raises(ErreurOutil) as exc:
        await get_contrat(appelant("orchestrateur"), FauxJetons(), dossiers, "X")
    assert exc.value.code == CONTRAT_INTROUVABLE


async def test_obo_refuse_dossiers_indisponibles_sans_appel_backend() -> None:
    dossiers = FauxDossiers()
    with pytest.raises(ErreurOutil) as exc:
        await get_contrat(appelant("orchestrateur"), FauxJetons(refuse=True), dossiers, "X")
    assert exc.value.code == DOSSIERS_INDISPONIBLES
    assert dossiers.appels == []
