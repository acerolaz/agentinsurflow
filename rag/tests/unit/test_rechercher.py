"""Unitaires — cas d'usage de recherche : porte, références exactes, ordre, refus propres."""

from __future__ import annotations

import pytest

from agentinsurflow_rag.application.use_cases.ingerer import ingerer
from agentinsurflow_rag.application.use_cases.rechercher import rechercher
from agentinsurflow_rag.domain.models import ResultatRecherche
from corpus_de_test import CORPUS, SHA
from fakes import FakeDepotCorpus, FakeEmbeddings

COLLECTIONS = ["textes_reglementaires"]


@pytest.fixture
async def depot() -> FakeDepotCorpus:
    d = FakeDepotCorpus()
    await ingerer(
        d, FakeEmbeddings(), collection=COLLECTIONS[0], instantane_sha256=SHA, articles=CORPUS
    )
    return d


async def _chercher(
    depot: FakeDepotCorpus,
    question: str,
    *,
    seuil: float = 0.4,  # entre le max hors corpus (0,31) et la question couverte (0,61)
    top_k: int = 5,
    collections: list[str] | None = None,
) -> ResultatRecherche:
    return await rechercher(
        depot,
        FakeEmbeddings(),
        question,
        seuil=seuil,
        top_k=top_k,
        candidats=20,
        collections=COLLECTIONS if collections is None else collections,
    )


async def test_question_couverte_cite_l_article(depot: FakeDepotCorpus) -> None:
    resultat = await _chercher(depot, "coefficient bonus malus appliqué à la prime")
    assert resultat.statut == "OK"
    assert resultat.resultats[0].citation.article == "A121-1"
    assert resultat.resultats[0].citation.url_source.startswith("https://www.legifrance.gouv.fr/")
    assert resultat.cosinus_max is not None and resultat.cosinus_max >= 0.4


async def test_question_hors_corpus_refusee(depot: FakeDepotCorpus) -> None:
    resultat = await _chercher(depot, "recette de la tarte aux pommes")
    assert (resultat.statut, resultat.resultats) == ("NOT_FOUND_IN_CORPUS", [])
    assert resultat.seuil == 0.4


async def test_reference_exacte_passe_meme_sous_le_seuil_et_vient_en_tete(
    depot: FakeDepotCorpus,
) -> None:
    resultat = await _chercher(depot, "Que dit l'article L. 211-2 ?", seuil=0.99)
    assert resultat.statut == "OK" and resultat.reference_exacte
    assert resultat.resultats[0].citation.article == "L211-2"
    assert resultat.resultats[0].cosinus is None


async def test_reference_inconnue_ne_passe_pas_la_porte(depot: FakeDepotCorpus) -> None:
    resultat = await _chercher(depot, "L999-9", seuil=0.99)
    assert resultat.statut == "NOT_FOUND_IN_CORPUS" and not resultat.reference_exacte


async def test_question_sans_mot_refusee(depot: FakeDepotCorpus) -> None:
    assert (await _chercher(depot, "???")).statut == "NOT_FOUND_IN_CORPUS"


async def test_base_vide_refus_propre() -> None:
    resultat = await _chercher(FakeDepotCorpus(), "assurance obligatoire du véhicule")
    assert (resultat.statut, resultat.cosinus_max) == ("NOT_FOUND_IN_CORPUS", None)


async def test_sans_collection_lisible_rien_n_est_lu(depot: FakeDepotCorpus) -> None:
    resultat = await _chercher(depot, "L211-1", seuil=0.0, collections=[])
    assert resultat.statut == "NOT_FOUND_IN_CORPUS"


async def test_top_k_et_sans_doublon(depot: FakeDepotCorpus) -> None:
    resultat = await _chercher(
        depot, "L211-1 responsabilité civile du véhicule", top_k=2, seuil=0.0
    )
    ids = [e.citation.chunk_id for e in resultat.resultats]
    assert len(ids) == 2 and len(set(ids)) == 2
    assert resultat.resultats[0].citation.article == "L211-1"


async def test_resultats_hybrides_ordonnes_par_rrf(depot: FakeDepotCorpus) -> None:
    resultat = await _chercher(depot, "responsabilité civile assurance véhicule", seuil=0.0)
    scores = [e.score_rrf for e in resultat.resultats]
    assert scores == sorted(scores, reverse=True)
