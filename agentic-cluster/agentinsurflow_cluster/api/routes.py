"""Routes : traduisent HTTP vers le service d'évaluation et le résultat vers un DTO."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from ..application.evaluation import (
    MESSAGE_REVUE_HUMAINE,
    AucuneRevueEnAttente,
    EvaluationEnAttente,
    Revue,
)
from ..domain.ports import ErreurOutil
from ..infrastructure.entra.verification import Gestionnaire
from ..infrastructure.langgraph.graphe import Resultat, ServiceEvaluation
from ..infrastructure.llm.fabrique import version_prompt
from .problemes import Probleme, reponse
from .schemas import (
    EtapeDto,
    EvaluationReponse,
    FicheDto,
    PrimeDto,
    RevueCorps,
    RevueReponse,
    SanteReponse,
)
from .securite import gestionnaire_courant

routeur = APIRouter()
AGENTS = ("pieces", "analyste", "redacteur", "actuaire")
_REPONSES: dict[int | str, dict[str, Any]] = {401: {}, 403: {}, 404: {}, 409: {}, 502: {}}

Courant = Annotated[Gestionnaire, Depends(gestionnaire_courant)]


def _service(request: Request) -> ServiceEvaluation:
    service: ServiceEvaluation | None = request.app.state.service
    if service is None:
        raise Probleme(503, "GARDE_FOUS_EN_CHARGEMENT", "Garde-fous en cours de chargement")
    return service


def _outil_en_echec(e: ErreurOutil) -> Probleme:
    if e.code == "CONTRAT_INTROUVABLE":
        return Probleme(404, "CONTRAT_INTROUVABLE", "Contrat introuvable")
    return Probleme(502, "OUTIL_INDISPONIBLE", "Un service du cluster est indisponible")


@routeur.get("/health", response_model=SanteReponse, responses={503: {}})
async def sante(request: Request) -> SanteReponse | JSONResponse:
    if request.app.state.service is None:
        return reponse(503, "GARDE_FOUS_EN_CHARGEMENT", "Garde-fous en cours de chargement")
    return SanteReponse(
        version=request.app.state.version,
        prompts={a: version_prompt(a) for a in AGENTS},  # type: ignore[arg-type]
        garde_fous="prets",
    )


def _evaluation(r: Resultat) -> EvaluationReponse:
    revue = r.statut == "REVUE_HUMAINE"
    e = r.etat
    return EvaluationReponse(
        statut=r.statut,  # type: ignore[arg-type]
        fiche=None if revue or e.fiche is None else FicheDto(**vars(e.fiche)),
        prime=None if revue or e.prime is None else PrimeDto(**vars(e.prime)),
        message=MESSAGE_REVUE_HUMAINE if revue else None,
        synthese=[EtapeDto(**t) for t in e.tours],  # type: ignore[arg-type]
    )


@routeur.post(
    "/evaluations/{numero_contrat}",
    response_model=EvaluationReponse,
    responses=_REPONSES,
)
async def evaluer(numero_contrat: str, request: Request, courant: Courant) -> EvaluationReponse:
    try:
        return _evaluation(await _service(request).evaluer(numero_contrat, courant.jeton))
    except EvaluationEnAttente as e:
        raise Probleme(
            409, "EVALUATION_EN_ATTENTE", "Une revue est déjà en attente pour ce dossier"
        ) from e
    except ErreurOutil as e:
        raise _outil_en_echec(e) from e


@routeur.post(
    "/evaluations/{numero_contrat}/revue",
    response_model=RevueReponse,
    responses=_REPONSES,
)
async def reviser(
    numero_contrat: str, corps: RevueCorps, request: Request, courant: Courant
) -> RevueReponse:
    revue = Revue(corps.decision, corps.validation, corps.motif)
    try:
        resultat = await _service(request).reviser(numero_contrat, revue, courant.jeton)
    except AucuneRevueEnAttente as e:
        raise Probleme(409, "AUCUNE_REVUE_EN_ATTENTE", "Aucune revue en attente") from e
    except ErreurOutil as e:
        raise _outil_en_echec(e) from e
    return RevueReponse(statut=resultat.statut)  # type: ignore[arg-type]
