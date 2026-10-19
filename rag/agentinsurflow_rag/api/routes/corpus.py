"""Ressources REST du corpus (S3-24) : ingestions, extraits, documents.

Routes minces : jeton et rôle d'abord (``exiger``), puis connexion du bon compte, puis cas d'usage.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response
from sqlalchemy.ext.asyncio import AsyncConnection

from ...application.use_cases.consulter import lire_document, lire_ingestion, lister_ingestions
from ...application.use_cases.ingerer import ingerer
from ...application.use_cases.rechercher import rechercher
from ...domain.corpus import collections_pour
from ...domain.models import Appelant
from ...domain.ports import ClientEmbeddings
from ...infrastructure.postgres.corpus import PgDepotCorpus
from ..dependances import (
    ConfigRag,
    charger_rag,
    connexion_reader,
    connexion_writer,
    obtenir_embeddings,
)
from ..erreurs import ErreurApi, reponses
from ..schemas.corpus import (
    DocumentDTO,
    IngestionDTO,
    LotIngestion,
    RapportIngestionDTO,
    ResultatRechercheDTO,
)
from ..securite import exiger

router = APIRouter(tags=["corpus"])

Ingestion = Annotated[Appelant, Depends(exiger("Ingestion"))]
Gestionnaire = Annotated[Appelant, Depends(exiger("Gestionnaire"))]
Ecriture = Annotated[AsyncConnection, Depends(connexion_writer)]
Lecture = Annotated[AsyncConnection, Depends(connexion_reader)]
Embeddings = Annotated[ClientEmbeddings, Depends(obtenir_embeddings)]


@router.post(
    "/api/ingestions",
    status_code=201,
    summary="Ingérer un lot d'articles (au plus 50) ; rapport journalisé",
    responses=reponses(401, 403, 503),
)
async def creer_ingestion(
    lot: LotIngestion,
    response: Response,
    _appelant: Ingestion,
    conn: Ecriture,
    emb: Embeddings,
) -> RapportIngestionDTO:
    rapport = await ingerer(
        PgDepotCorpus(conn),
        emb,
        collection=lot.collection,
        instantane_sha256=lot.instantane_sha256,
        articles=[a.model_dump() for a in lot.articles],
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
    resultat = await rechercher(
        PgDepotCorpus(conn),
        emb,
        question,
        seuil=cfg.rag_seuil,
        top_k=top_k or cfg.rag_top_k,
        candidats=cfg.rag_candidats,
        collections=collections_pour(appelant.roles),
    )
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
