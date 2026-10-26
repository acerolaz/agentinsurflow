"""Consultation du corpus : traçabilité d'un article et journal des ingestions."""

from __future__ import annotations

from ...domain.attribution import Attribution, VersionIntrouvable
from ...domain.corpus import COLLECTION_S3
from ...domain.models import DocumentTrace, EtatCorpus, IngestionJournalisee
from ...domain.ports import DepotCorpus


async def lire_document(
    depot: DepotCorpus, doc_id: str, collections: list[str]
) -> DocumentTrace | None:
    """Un article et ses versions, seulement s'il est dans une collection lisible par l'appelant."""
    document = await depot.document(doc_id)
    return document if document is not None and document.collection in collections else None


async def attribuer(
    depot: DepotCorpus, doc_id: str, version: str | None, collections: list[str]
) -> Attribution | None:
    """Mentions Etalab d'une version d'article (par défaut la courante, une obsolète reste citable).

    ``None`` si l'article est inconnu, hors des collections, ou rédigé pour le projet (seuls les
    textes Légifrance relèvent d'Etalab) ; ``VersionIntrouvable`` sinon.
    """
    document = await lire_document(depot, doc_id, collections)
    if document is None or document.collection != COLLECTION_S3:
        return None
    choisie = next(
        (v for v in document.versions if (v.version == version if version else not v.obsolete)),
        None,
    )
    if choisie is None:
        raise VersionIntrouvable(version or doc_id)
    article = next((c.article for c in document.chunks if c.version == choisie.version), None)
    if article is None:
        raise VersionIntrouvable(choisie.version)  # aucun extrait : rien à attribuer
    return Attribution(
        doc_id, article, choisie.version, choisie.date_debut, choisie.url_source, choisie.extrait_le
    )


async def lister_ingestions(
    depot: DepotCorpus, limit: int, offset: int
) -> list[IngestionJournalisee]:
    return await depot.ingestions(limit, offset)


async def lire_ingestion(depot: DepotCorpus, ingestion_id: int) -> IngestionJournalisee | None:
    return await depot.ingestion(ingestion_id)


async def etat_du_corpus(depot: DepotCorpus) -> EtatCorpus:
    return await depot.etat()
