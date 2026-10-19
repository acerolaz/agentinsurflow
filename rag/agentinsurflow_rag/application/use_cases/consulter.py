"""Consultation du corpus : traçabilité d'un article et journal des ingestions."""

from __future__ import annotations

from ...domain.models import DocumentTrace, IngestionJournalisee
from ...domain.ports import DepotCorpus


async def lire_document(
    depot: DepotCorpus, doc_id: str, collections: list[str]
) -> DocumentTrace | None:
    """Un article et ses versions, seulement s'il est dans une collection lisible par l'appelant."""
    document = await depot.document(doc_id)
    return document if document is not None and document.collection in collections else None


async def lister_ingestions(
    depot: DepotCorpus, limit: int, offset: int
) -> list[IngestionJournalisee]:
    return await depot.ingestions(limit, offset)


async def lire_ingestion(depot: DepotCorpus, ingestion_id: int) -> IngestionJournalisee | None:
    return await depot.ingestion(ingestion_id)
