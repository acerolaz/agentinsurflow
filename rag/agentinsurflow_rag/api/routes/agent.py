"""Ressource REST de l'agent (S3-24) : ``POST /api/reponses``.

Ordre : jeton et rôle → dossier (si ``numero_contrat`` : OBO puis BOLA chez underwriting-admin)
→ recherche (porte) → agent (verrous ② et ③). Le dossier passe avant la recherche : un contrat
refusé n'appelle ni les embeddings ni le LLM.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncConnection

from ...application.use_cases.consulter_contrat import consulter_contrat
from ...application.use_cases.repondre import repondre
from ...domain.corpus import hash_contenu
from ...domain.models import Appelant, CitationRag
from ...domain.ports import ClientEmbeddings, ClientLLM, DepotDossiers
from ...infrastructure.azure_openai.config import charger_config
from ...infrastructure.azure_openai.llm import fabrique_llm
from ...infrastructure.entra.obo import ConfigObo, jeton_obo
from ...infrastructure.otel.telemetrie import trace_id_courant, tracer
from ...infrastructure.underwriting.client import ClientUnderwriting
from ..dependances import ConfigRag, charger_rag, connexion_reader, obtenir_embeddings
from ..erreurs import reponses
from ..recherche import chercher
from ..schemas.agent import Question, ReponseDTO
from ..securite import Jeton, exiger

router = APIRouter(tags=["agent"])

DELAI_UNDERWRITING_S = 10


def obtenir_llm() -> ClientLLM | None:
    # ponytail: client recréé à chaque requête (~500/jour) ; au lifespan si la latence compte
    return fabrique_llm(charger_config())


async def obtenir_dossiers(jeton: Jeton) -> AsyncIterator[DepotDossiers | None]:
    """Accès aux dossiers au nom du gestionnaire (OBO), ou None si non configuré."""
    try:
        cfg = ConfigObo()  # type: ignore[call-arg]
    except ValidationError:
        yield None
        return
    if jeton is None:
        yield None
        return
    jeton_utilisateur = jeton.credentials

    async def obo() -> str:
        return await run_in_threadpool(jeton_obo, cfg, jeton_utilisateur)

    async with httpx.AsyncClient(timeout=DELAI_UNDERWRITING_S) as http:
        yield ClientUnderwriting(http, cfg.underwriting_url, obo)


@router.post(
    "/api/reponses",
    summary="Réponse citée de l'agent, ou refus hors corpus (NOT_FOUND_IN_CORPUS)",
    responses=reponses(401, 403, 404, 503),
)
async def creer_reponse(
    q: Question,
    appelant: Annotated[Appelant, Depends(exiger("Gestionnaire"))],
    conn: Annotated[AsyncConnection, Depends(connexion_reader)],
    emb: Annotated[ClientEmbeddings, Depends(obtenir_embeddings)],
    cfg: Annotated[ConfigRag, Depends(charger_rag)],
    llm: Annotated[ClientLLM | None, Depends(obtenir_llm)],
    dossiers: Annotated[DepotDossiers | None, Depends(obtenir_dossiers)],
) -> ReponseDTO:
    with tracer.start_as_current_span("agent.repondre") as span:
        span.set_attributes(
            {
                "question.sha256": hash_contenu(q.texte),
                "question.longueur": len(q.texte),
                "contrat.present": q.numero_contrat is not None,
            }
        )
        contrat = await consulter_contrat(dossiers, q.numero_contrat) if q.numero_contrat else None
        recherche = await chercher(conn, emb, cfg, appelant, q.texte)
        reponse = await run_in_threadpool(repondre, q.texte, recherche, llm, contrat)
        span.set_attributes(
            {
                "agent.statut": reponse.statut,
                "agent.verrou": str(reponse.verrou) if reponse.verrou else "aucun",
                "agent.articles_cites": [
                    c.article for c in reponse.citations if isinstance(c, CitationRag)
                ],
            }
        )
        return ReponseDTO.depuis(reponse, trace_id_courant())
