"""Garde ASGI de ``/mcp`` : jeton Entra (Bearer) et rôle ``Gestionnaire``, refus par défaut.

Un middleware (pas une dépendance FastAPI) : la route ``/mcp`` appartient au SDK MCP. L'appelant
validé est publié dans ``appelant_courant`` pour toute la durée de la requête, réponse en flux
(SSE) comprise ; ``ServeurMcp`` le lit pour filtrer et autoriser les outils.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from jwt import PyJWKClient, PyJWTError
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from ..domain.models import Appelant
from ..infrastructure.entra.jetons import ConfigAuth, ErreurAuth, verifier_jeton

appelant_courant: ContextVar[Appelant | None] = ContextVar("appelant_courant", default=None)

NON_AUTHENTIFIE = {"WWW-Authenticate": "Bearer"}
ROLE = "Gestionnaire"


def _probleme(statut: int, code: str, titre: str, entetes: dict[str, str] | None = None) -> Any:
    return JSONResponse(
        {"type": "about:blank", "title": titre, "status": statut, "code": code},
        status_code=statut,
        media_type="application/problem+json",
        headers=entetes,
    )


def _bearer(scope: Scope) -> str | None:
    for nom, valeur in scope["headers"]:
        if nom == b"authorization":
            schema, _, jeton = valeur.decode("latin-1").partition(" ")
            return jeton.strip() or None if schema.lower() == "bearer" else None
    return None


class GardeMcp:
    """Protège le chemin ``/mcp`` ; le reste de l'application (``/health``) passe."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"].rstrip("/") != "/mcp":
            await self.app(scope, receive, send)
            return
        etat = scope["app"].state
        jeton = _bearer(scope)
        if jeton is None:
            reponse = _probleme(401, "JETON_ABSENT", "Jeton absent", NON_AUTHENTIFIE)
        else:
            reponse = self._valider(etat.config_auth, etat.jwks, jeton)
        if isinstance(reponse, Appelant):
            marque = appelant_courant.set(reponse)
            try:
                await self.app(scope, receive, send)
            finally:
                appelant_courant.reset(marque)
            return
        await reponse(scope, receive, send)

    @staticmethod
    def _valider(cfg: ConfigAuth | None, jwks: PyJWKClient | None, jeton: str) -> Any:
        if cfg is None or jwks is None:
            return _probleme(503, "AUTH_INDISPONIBLE", "Authentification Entra non configurée")
        try:
            cle = jwks.get_signing_key_from_jwt(jeton).key
            appelant = verifier_jeton(jeton, cle, cfg)
        except (PyJWTError, ErreurAuth):
            return _probleme(401, "JETON_INVALIDE", "Jeton invalide", NON_AUTHENTIFIE)
        if ROLE not in appelant.roles:
            return _probleme(403, "ROLE_MANQUANT", f"Rôle {ROLE} requis")
        return appelant
