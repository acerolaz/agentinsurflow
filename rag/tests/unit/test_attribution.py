"""Unitaires — attribution Etalab 2.0 d'une version d'article."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from agentinsurflow_rag.application.use_cases.consulter import attribuer
from agentinsurflow_rag.domain.attribution import VersionIntrouvable
from agentinsurflow_rag.domain.models import ChunkDocument, DocumentTrace, VersionDocument

COLLECTIONS = ["textes_reglementaires"]


def _version(version: str, *, obsolete: bool, extrait_le: date) -> VersionDocument:
    return VersionDocument(
        version=version,
        etat="VIGUEUR",
        date_debut=date(2003, 1, 1),
        hash_contenu="h",
        obsolete=obsolete,
        ingere_le=datetime(2026, 10, 1, tzinfo=UTC),
        url_source=f"https://www.legifrance.gouv.fr/codes/article_lc/{version}",
        extrait_le=extrait_le,
    )


class _DepotDocument:
    """Seule la lecture d'un article est utile ici : le reste du port n'est pas sollicité."""

    def __init__(self, document: DocumentTrace) -> None:
        self._document = document

    async def document(self, doc_id: str) -> DocumentTrace | None:
        return self._document if doc_id == self._document.doc_id else None


def _depot(*, v2_obsolete: bool = False) -> _DepotDocument:
    versions = [
        _version("v1", obsolete=True, extrait_le=date(2026, 9, 1)),
        _version("v2", obsolete=v2_obsolete, extrait_le=date(2026, 10, 20)),
    ]
    chunks = [
        ChunkDocument(1, "v1", "L211-0", 0, "ancien"),
        ChunkDocument(2, "v2", "L211-1", 0, "courant"),
    ]
    return _DepotDocument(DocumentTrace("LEGIARTI1", "textes_reglementaires", versions, chunks))


async def test_attribution_de_la_version_courante_par_defaut():
    a = await attribuer(_depot(), "LEGIARTI1", None, COLLECTIONS)
    assert a is not None
    assert (a.version, a.article, a.mise_a_jour_le) == ("v2", "L211-1", date(2026, 10, 20))
    assert (a.source, a.concedant) == (
        "Légifrance",
        "Direction de l'information légale et administrative (DILA)",
    )
    assert a.licence_url == "https://www.etalab.gouv.fr/licence-ouverte-open-licence/"


async def test_attribution_d_une_version_obsolete_demandee():
    a = await attribuer(_depot(), "LEGIARTI1", "v1", COLLECTIONS)
    assert a is not None
    assert (a.version, a.article, a.mise_a_jour_le) == ("v1", "L211-0", date(2026, 9, 1))


async def test_version_inconnue_leve_version_introuvable():
    with pytest.raises(VersionIntrouvable):
        await attribuer(_depot(), "LEGIARTI1", "v9", COLLECTIONS)


async def test_sans_version_courante_leve_version_introuvable():
    with pytest.raises(VersionIntrouvable):
        await attribuer(_depot(v2_obsolete=True), "LEGIARTI1", None, COLLECTIONS)


async def test_article_inconnu_ou_hors_collection_rend_none():
    assert await attribuer(_depot(), "INCONNU", None, COLLECTIONS) is None
    assert await attribuer(_depot(), "LEGIARTI1", None, ["autre"]) is None
