"""Ressources REST du corpus (S3-24) : ingestions, extraits, documents.

Routes minces : jeton et rôle d'abord (``exiger``), puis connexion du bon compte, puis cas d'usage.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from ...application.use_cases.consulter import (
    attribuer,
    lire_document,
    lire_ingestion,
    lister_ingestions,
)
from ...application.use_cases.ingerer import ingerer
from ...domain.attribution import VersionIntrouvable
from ...domain.corpus import collections_pour
from ...domain.models import Appelant
from ...domain.ports import ClientEmbeddings
from ...infrastructure.otel.telemetrie import tracer
from ...infrastructure.postgres.corpus import PgDepotCorpus
from ..dependances import (
    ConfigRag,
    charger_rag,
    connexion_reader,
    connexion_writer,
    obtenir_embeddings,
)
from ..erreurs import ErreurApi, reponses
from ..recherche import chercher
from ..schemas.corpus import (
    AttributionDTO,
    DocumentDTO,
    IngestionDTO,
    LicenceDTO,
    LotIngestion,
    RapportIngestionDTO,
    ResultatRechercheDTO,
)
from ..securite import exiger

router = APIRouter(tags=["corpus"])

Ingestion = Annotated[Appelant, Depends(exiger("Ingestion"))]
Gestionnaire = Annotated[Appelant, Depends(exiger("Gestionnaire"))]
# portée « function » : COMMIT avant l'envoi de la 201 (un COMMIT raté ne doit pas se perdre)
Ecriture = Annotated[AsyncConnection, Depends(connexion_writer, scope="function")]
Lecture = Annotated[AsyncConnection, Depends(connexion_reader)]
Embeddings = Annotated[ClientEmbeddings, Depends(obtenir_embeddings)]


@router.post(
    "/api/ingestions",
    status_code=201,
    summary="Ingérer un lot d'articles (au plus 50) ; rapport journalisé",
    responses=reponses(401, 403, 409, 503),
)
async def creer_ingestion(
    lot: LotIngestion,
    response: Response,
    _appelant: Ingestion,
    conn: Ecriture,
    emb: Embeddings,
) -> RapportIngestionDTO:
    with tracer.start_as_current_span("ingestion.lot") as span:
        try:
            rapport = await ingerer(
                PgDepotCorpus(conn),
                emb,
                collection=lot.collection,
                instantane_sha256=lot.instantane_sha256,
                instantane_date=lot.instantane_date,
                articles=[a.model_dump() for a in lot.articles],
            )
        except IntegrityError as exc:  # un lot concurrent a écrit le même article ; lot annulé
            raise ErreurApi(
                409, "CONFLIT_INGESTION", "Lot concurrent sur les mêmes articles : rejouer le lot"
            ) from exc
        span.set_attributes(
            {
                "rag.collection": lot.collection,
                "rag.inseres": rapport.inseres,
                "rag.inchanges": rapport.inchanges,
                "rag.rejets": len(rapport.rejets),
                "rag.quasi_doublons": len(rapport.quasi_doublons),
            }
        )
    response.headers["Location"] = f"/api/ingestions/{rapport.id}"
    return RapportIngestionDTO.model_validate(rapport)


@router.get(
    "/api/ingestions",
    summary="Rapports d'ingestion, du plus récent au plus ancien",
    responses=reponses(401, 403, 503),
)
async def lister_les_ingestions(
    _appelant: Ingestion,
    conn: Lecture,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[IngestionDTO]:
    lignes = await lister_ingestions(PgDepotCorpus(conn), limit, offset)
    return [IngestionDTO.model_validate(ligne) for ligne in lignes]


@router.get(
    "/api/ingestions/{ingestion_id}",
    summary="Un rapport d'ingestion",
    responses=reponses(401, 403, 404, 503),
)
async def lire_une_ingestion(
    ingestion_id: Annotated[int, Path(ge=1)], _appelant: Ingestion, conn: Lecture
) -> IngestionDTO:
    ligne = await lire_ingestion(PgDepotCorpus(conn), ingestion_id)
    if ligne is None:
        raise ErreurApi(404, "INGESTION_INTROUVABLE", "Ingestion introuvable")
    return IngestionDTO.model_validate(ligne)


@router.get(
    "/api/extraits",
    summary="Extraits du corpus qui passent la porte de pertinence (NOT_FOUND_IN_CORPUS sinon)",
    responses=reponses(401, 403, 503),
)
async def lister_les_extraits(
    question: Annotated[str, Query(min_length=1, max_length=2000)],
    appelant: Gestionnaire,
    conn: Lecture,
    emb: Embeddings,
    cfg: Annotated[ConfigRag, Depends(charger_rag)],
    top_k: Annotated[int | None, Query(ge=1, le=20)] = None,
) -> ResultatRechercheDTO:
    resultat = await chercher(conn, emb, cfg, appelant, question, top_k)
    return ResultatRechercheDTO.model_validate(resultat)


@router.get(
    "/api/documents/{doc_id}",
    summary="Traçabilité d'un article : ses versions et ses chunks (sans les vecteurs)",
    responses=reponses(401, 403, 404, 503),
)
async def lire_un_document(doc_id: str, appelant: Gestionnaire, conn: Lecture) -> DocumentDTO:
    document = await lire_document(PgDepotCorpus(conn), doc_id, collections_pour(appelant.roles))
    if document is None:
        raise ErreurApi(404, "DOCUMENT_INTROUVABLE", "Document introuvable")
    return DocumentDTO.model_validate(document)


@router.get(
    "/api/documents/{doc_id}/attribution",
    summary="Mentions d'attribution Etalab 2.0 d'un article (version courante par défaut)",
    responses=reponses(401, 403, 404, 503),
)
async def lire_l_attribution(
    doc_id: str,
    appelant: Gestionnaire,
    conn: Lecture,
    version: Annotated[
        str | None,
        Query(
            min_length=1,
            description="Facultatif : version courante par défaut ; une version obsolète "
            "reste attribuable",
            examples=["2023-01-01"],
        ),
    ] = None,
) -> AttributionDTO:
    try:
        attribution = await attribuer(
            PgDepotCorpus(conn), doc_id, version, collections_pour(appelant.roles)
        )
    except VersionIntrouvable as exc:
        raise ErreurApi(404, "VERSION_INTROUVABLE", "Version introuvable pour cet article") from exc
    if attribution is None:
        raise ErreurApi(404, "DOCUMENT_INTROUVABLE", "Document introuvable")
    return AttributionDTO(
        doc_id=attribution.doc_id,
        article=attribution.article,
        version=attribution.version,
        date_debut=attribution.date_debut,
        url_source=attribution.url_source,
        source=attribution.source,
        concedant=attribution.concedant,
        licence=LicenceDTO(nom=attribution.licence_nom, url=attribution.licence_url),
        mise_a_jour_le=attribution.mise_a_jour_le,
        modifications=attribution.modifications,
    )
