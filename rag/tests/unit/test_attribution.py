"""Unitaires — attribution Etalab 2.0 d'une version d'article (port simulé : dépôt en mémoire)."""

from __future__ import annotations

from datetime import date

import pytest

from agentinsurflow_rag.application.use_cases.consulter import attribuer
from agentinsurflow_rag.domain.attribution import VersionIntrouvable
from agentinsurflow_rag.domain.models import ArticlePropre
from fakes import FakeDepotCorpus

COLLECTIONS = ["textes_reglementaires"]


def _article(version: str, numero: str) -> ArticlePropre:
    return ArticlePropre(
        doc_id="LEGIARTI1",
        version=version,
        article=numero,
        date_debut=date(2003, 1, 1),
        etat="VIGUEUR",
        url_source=f"https://www.legifrance.gouv.fr/codes/article_lc/{version}",
        texte="texte",
        hash_contenu=f"h{version}",
    )


async def _depot(*, v2_obsolete: bool = False, v2_chunks: bool = True) -> FakeDepotCorpus:
    depot = FakeDepotCorpus()
    await depot.inserer(
        _article("v1", "L211-0"), "textes_reglementaires", ["ancien"], [[1.0]], date(2026, 9, 1)
    )
    await depot.marquer_obsolete(1)
    chunks, vecteurs = (["courant"], [[1.0]]) if v2_chunks else ([], [])
    await depot.inserer(
        _article("v2", "L211-1"), "textes_reglementaires", chunks, vecteurs, date(2026, 10, 20)
    )
    if v2_obsolete:
        await depot.marquer_obsolete(2)
    return depot


async def test_attribution_de_la_version_courante_par_defaut() -> None:
    a = await attribuer(await _depot(), "LEGIARTI1", None, COLLECTIONS)
    assert a is not None
    assert (a.version, a.article, a.mise_a_jour_le) == ("v2", "L211-1", date(2026, 10, 20))
    assert (a.source, a.concedant) == (
        "Légifrance",
        "Direction de l'information légale et administrative (DILA)",
    )
    assert a.licence_url == "https://www.etalab.gouv.fr/licence-ouverte-open-licence/"


async def test_attribution_d_une_version_obsolete_demandee():
    a = await attribuer(await _depot(), "LEGIARTI1", "v1", COLLECTIONS)
    assert a is not None
    assert (a.version, a.article, a.mise_a_jour_le) == ("v1", "L211-0", date(2026, 9, 1))


async def test_version_inconnue_leve_version_introuvable():
    with pytest.raises(VersionIntrouvable):
        await attribuer(await _depot(), "LEGIARTI1", "v9", COLLECTIONS)


async def test_sans_version_courante_leve_version_introuvable():
    with pytest.raises(VersionIntrouvable):
        await attribuer(await _depot(v2_obsolete=True), "LEGIARTI1", None, COLLECTIONS)


async def test_version_sans_extrait_leve_version_introuvable():
    with pytest.raises(VersionIntrouvable):
        await attribuer(await _depot(v2_chunks=False), "LEGIARTI1", None, COLLECTIONS)


async def test_article_inconnu_ou_hors_collection_rend_none():
    depot = await _depot()
    assert await attribuer(depot, "INCONNU", None, COLLECTIONS) is None
    assert await attribuer(depot, "LEGIARTI1", None, ["autre"]) is None
