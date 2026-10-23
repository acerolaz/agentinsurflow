"""ProblemDetails (``application/problem+json``) avec un ``code`` stable."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class Probleme(Exception):
    def __init__(
        self, statut: int, code: str, titre: str, entetes: dict[str, str] | None = None
    ) -> None:
        super().__init__(code)
        self.statut, self.code, self.titre, self.entetes = statut, code, titre, entetes


def reponse(
    statut: int, code: str, titre: str, entetes: dict[str, str] | None = None, **extra: Any
) -> JSONResponse:
    return JSONResponse(
        {"type": "about:blank", "title": titre, "status": statut, "code": code, **extra},
        status_code=statut,
        media_type="application/problem+json",
        headers=entetes,
    )


def installer(app: FastAPI) -> None:
    @app.exception_handler(Probleme)
    async def _probleme(_: Request, e: Probleme) -> JSONResponse:
        return reponse(e.statut, e.code, e.titre, e.entetes)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, e: RequestValidationError) -> JSONResponse:
        # 422 : seuls les champs fautifs sont nommés, jamais la valeur saisie (le motif est libre)
        champs = [".".join(str(p) for p in err["loc"][1:]) for err in e.errors()]
        return reponse(422, "REQUETE_INVALIDE", "Requête invalide", champs=champs)
