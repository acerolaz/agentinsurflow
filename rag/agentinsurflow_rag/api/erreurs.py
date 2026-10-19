"""Erreurs de l'API au format ProblemDetails (RFC 9457), avec un champ ``code`` (S3-24)."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class ErreurApi(Exception):
    def __init__(
        self, statut: int, code: str, titre: str, entetes: dict[str, str] | None = None
    ) -> None:
        super().__init__(titre)
        self.statut, self.code, self.titre, self.entetes = statut, code, titre, entetes


def probleme(
    statut: int, code: str, titre: str, entetes: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(
        {"type": "about:blank", "title": titre, "status": statut, "code": code},
        status_code=statut,
        media_type="application/problem+json",
        headers=entetes,
    )


async def _gerer(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ErreurApi)
    return probleme(exc.statut, exc.code, exc.titre, exc.entetes)


def installer_gestionnaires(app: FastAPI) -> None:
    app.add_exception_handler(ErreurApi, _gerer)
