"""Erreurs de l'API au format ProblemDetails (RFC 9457), avec un champ ``code`` (S3-24)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..domain.ports import ContratIntrouvable, ErreurDossiers, ErreurEmbeddings


class ErreurApi(Exception):
    def __init__(
        self, statut: int, code: str, titre: str, entetes: dict[str, str] | None = None
    ) -> None:
        super().__init__(titre)
        self.statut, self.code, self.titre, self.entetes = statut, code, titre, entetes


class Probleme(BaseModel):
    """Corps d'erreur (RFC 9457) ; ``code`` est stable et sert aux clients."""

    type: str = "about:blank"
    title: str
    status: int
    code: str


def probleme(
    statut: int, code: str, titre: str, entetes: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(
        Probleme(title=titre, status=statut, code=code).model_dump(),
        status_code=statut,
        media_type="application/problem+json",
        headers=entetes,
    )


def reponses(*statuts: int) -> dict[int | str, dict[str, Any]]:
    """Réponses d'erreur déclarées dans l'OpenAPI d'une route."""
    libelles = {
        401: "Jeton absent ou invalide (JETON_ABSENT, JETON_INVALIDE)",
        403: "Rôle d'app manquant (ROLE_MANQUANT)",
        404: "Ressource introuvable (CONTRAT_INTROUVABLE, DOCUMENT_INTROUVABLE…)",
        503: "Dépendance indisponible (EMBEDDINGS_INDISPONIBLES, DOSSIERS_INDISPONIBLES…)",
    }
    return {
        s: {
            "model": Probleme,
            "description": libelles[s],
            "content": {"application/problem+json": {}},
        }
        for s in statuts
    }


async def _gerer(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ErreurApi)
    return probleme(exc.statut, exc.code, exc.titre, exc.entetes)


async def _embeddings(request: Request, exc: Exception) -> JSONResponse:
    return probleme(503, "EMBEDDINGS_INDISPONIBLES", "Le modèle d'embeddings ne répond pas")


async def _dossiers(request: Request, exc: Exception) -> JSONResponse:
    return probleme(503, "DOSSIERS_INDISPONIBLES", "Les dossiers ne sont pas joignables")


async def _contrat(request: Request, exc: Exception) -> JSONResponse:
    # même réponse pour un contrat absent et un contrat d'un autre gestionnaire (BOLA)
    return probleme(404, "CONTRAT_INTROUVABLE", "Contrat introuvable")


def installer_gestionnaires(app: FastAPI) -> None:
    app.add_exception_handler(ErreurApi, _gerer)
    app.add_exception_handler(ErreurEmbeddings, _embeddings)
    app.add_exception_handler(ErreurDossiers, _dossiers)
    app.add_exception_handler(ContratIntrouvable, _contrat)
