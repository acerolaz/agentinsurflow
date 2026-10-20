"""Unitaires — cas d'usage d'ingestion (ports simulés : dépôt en mémoire, FakeEmbeddings)."""

from __future__ import annotations

from typing import Any

import pytest

from agentinsurflow_rag.application.use_cases.ingerer import ingerer
from agentinsurflow_rag.domain.models import QuasiDoublon, RapportIngestion, Rejet
from agentinsurflow_rag.domain.ports import ErreurEmbeddings
from corpus_de_test import CORPUS, SHA, article
from fakes import FakeDepotCorpus, FakeEmbeddings


async def _ingerer(
    depot: FakeDepotCorpus, articles: list[dict[str, Any]], emb: FakeEmbeddings | None = None
) -> RapportIngestion:
    return await ingerer(
        depot,
        emb or FakeEmbeddings(),
        collection="textes_reglementaires",
        instantane_sha256=SHA,
        articles=articles,
    )


async def test_lot_insere_puis_rejeu_idempotent() -> None:
    depot = FakeDepotCorpus()
    premier = await _ingerer(depot, CORPUS)
    second = await _ingerer(depot, CORPUS)
    assert (premier.lus, premier.inseres, premier.inchanges) == (4, 4, 0)
    assert (second.inseres, second.inchanges, second.nouvelles_versions) == (0, 4, 0)
    assert len(depot.documents) == 4


async def test_nouvelle_version_rend_l_ancienne_obsolete() -> None:
    depot = FakeDepotCorpus()
    await _ingerer(depot, CORPUS[:1])
    modifie = CORPUS[0] | {
        "version": "v2",
        "texte_html": "<p>Texte modifié de l'article, assez long.</p>",
    }
    rapport = await _ingerer(depot, [modifie])
    assert (rapport.nouvelles_versions, rapport.inseres) == (1, 0)
    courants = [d for d in depot.documents if not d.obsolete]
    assert [d.article.version for d in courants] == ["v2"]


async def test_rejeu_d_un_instantane_plus_ancien_rejete_sans_conflit() -> None:
    depot = FakeDepotCorpus()
    await _ingerer(depot, CORPUS[:1])  # v1
    v2 = CORPUS[0] | {
        "version": "v2",
        "texte_html": "<p>Texte modifié de l'article, assez long.</p>",
    }
    await _ingerer(depot, [v2])
    rapport = await _ingerer(depot, CORPUS[:1])  # l'ancien instantané rejoué (rollback)
    assert rapport.rejets == [Rejet(CORPUS[0]["doc_id"], "version_anterieure")]
    assert (rapport.inseres, rapport.nouvelles_versions, len(depot.documents)) == (0, 0, 2)
    assert [d.article.version for d in depot.documents if not d.obsolete] == ["v2"]


async def test_contenu_modifie_sous_la_meme_version_rejete() -> None:
    depot = FakeDepotCorpus()
    await _ingerer(depot, CORPUS[:1])
    rapport = await _ingerer(
        depot, [CORPUS[0] | {"texte_html": "<p>Autre texte, même version.</p>"}]
    )
    assert rapport.rejets == [Rejet(CORPUS[0]["doc_id"], "conflit_version")]
    assert len(depot.documents) == 1


async def test_article_partiel_rejete_sans_bloquer_le_lot() -> None:
    depot = FakeDepotCorpus()
    sans_texte = {k: v for k, v in CORPUS[2].items() if k != "texte_html"}
    rapport = await _ingerer(depot, [CORPUS[0], CORPUS[1], sans_texte])
    assert rapport.inseres == 2
    assert rapport.rejets == [Rejet(CORPUS[2]["doc_id"], "partiel:texte_html")]


async def test_quasi_doublon_signale_pas_rejete() -> None:
    depot = FakeDepotCorpus()
    jumeau = article("LEGIARTI_JUMEAU", "L. 211-1-1", CORPUS[0]["texte_html"][3:-4])
    rapport = await _ingerer(depot, [CORPUS[0], jumeau])
    assert rapport.inseres == 2
    assert len(rapport.quasi_doublons) == 1
    doublon = rapport.quasi_doublons[0]
    assert (doublon.doc_id, doublon.proche_de) == ("LEGIARTI_JUMEAU", CORPUS[0]["doc_id"])
    assert doublon.score > 0.95 and isinstance(doublon, QuasiDoublon)


async def test_embeddings_en_panne_rien_n_est_ecrit() -> None:
    depot = FakeDepotCorpus()
    with pytest.raises(ErreurEmbeddings):
        await _ingerer(depot, CORPUS, FakeEmbeddings(erreur=ErreurEmbeddings("panne")))
    assert depot.documents == [] and depot.journal == []


async def test_un_seul_appel_d_embeddings_par_lot() -> None:
    emb = FakeEmbeddings()
    await _ingerer(FakeDepotCorpus(), CORPUS, emb)
    assert len(emb.appels) == 1 and len(emb.appels[0]) == 4


async def test_lot_sans_rien_a_indexer_n_appelle_pas_les_embeddings() -> None:
    depot, emb = FakeDepotCorpus(), FakeEmbeddings()
    await _ingerer(depot, CORPUS[:1])
    await _ingerer(depot, CORPUS[:1] + [{"doc_id": "X"}], emb)
    assert emb.appels == []


async def test_article_long_plusieurs_chunks() -> None:
    depot = FakeDepotCorpus()
    long = article("LEGIARTI_LONG", "L. 211-8", "</p><p>".join(["mot " * 300] * 3))
    await _ingerer(depot, [long])
    assert len(depot.chunks) >= 2
    assert [c.ordre for c in depot.chunks] == list(range(len(depot.chunks)))


async def test_rapport_journalise_avec_son_id() -> None:
    depot = FakeDepotCorpus()
    rapport = await _ingerer(depot, CORPUS[:2])
    assert rapport.id == 1
    (ligne,) = depot.journal
    assert ligne.instantane_sha256 == SHA
    assert ligne.rapport["inseres"] == 2 and ligne.rapport["lus"] == 2
    assert rapport.duree_s >= 0


async def test_doc_id_deux_fois_dans_le_lot_rejete() -> None:
    depot = FakeDepotCorpus()
    v2 = CORPUS[0] | {"version": "v2", "texte_html": "<p>Autre texte de l'article, assez long.</p>"}
    rapport = await _ingerer(depot, [CORPUS[0], v2])
    assert rapport.inseres == 1 and rapport.nouvelles_versions == 0
    assert rapport.rejets == [Rejet(CORPUS[0]["doc_id"], "doublon_dans_le_lot")]
