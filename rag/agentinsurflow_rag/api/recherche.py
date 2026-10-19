"""Recherche tracée (span ``rag.recherche``) pour ``/api/extraits`` et ``/api/reponses``."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncConnection

from ..application.use_cases.rechercher import rechercher
from ..domain.corpus import collections_pour
from ..domain.models import Appelant, ResultatRecherche
from ..domain.ports import ClientEmbeddings
from ..infrastructure.otel.telemetrie import tracer
from ..infrastructure.postgres.corpus import PgDepotCorpus
from .dependances import ConfigRag


async def chercher(
    conn: AsyncConnection,
    emb: ClientEmbeddings,
    cfg: ConfigRag,
    appelant: Appelant,
    question: str,
    top_k: int | None = None,
) -> ResultatRecherche:
    with tracer.start_as_current_span("rag.recherche") as span:
        resultat = await rechercher(
            PgDepotCorpus(conn),
            emb,
            question,
            seuil=cfg.rag_seuil,
            top_k=top_k or cfg.rag_top_k,
            candidats=cfg.rag_candidats,
            collections=collections_pour(appelant.roles),
        )
        span.set_attributes(
            {
                "rag.statut": resultat.statut,
                "rag.seuil": resultat.seuil,
                "rag.reference_exacte": resultat.reference_exacte,
                "rag.articles": [e.citation.article for e in resultat.resultats],
            }
        )
        if resultat.cosinus_max is not None:
            span.set_attribute("rag.cosinus_max", resultat.cosinus_max)
        return resultat
