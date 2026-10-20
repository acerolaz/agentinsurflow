"""Authentification des routes de rag : jeton Entra (Bearer) et rôle d'app, refus par défaut.

Chaque route protégée déclare ``Depends(exiger("<rôle>"))`` ; sans cette déclaration, une route
ne lit rien du corpus (aucune connexion n'est fournie hors de ces dépendances).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any, Literal

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError
from pydantic import ValidationError

from ..domain.models import Appelant
from ..infrastructure.entra.jetons import ConfigAuth, ErreurAuth, verifier_jeton
from .erreurs import ErreurApi

Role = Literal["Gestionnaire", "Ingestion"]

bearer = HTTPBearer(auto_error=False, scheme_name="entra", description="Jeton Entra ID")
Jeton = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]

NON_AUTHENTIFIE = {"WWW-Authenticate": "Bearer"}


AUTH_INDISPONIBLE = ErreurApi(503, "AUTH_INDISPONIBLE", "Authentification Entra non configurée")


def charger_auth() -> ConfigAuth:
    try:
        return ConfigAuth()  # type: ignore[call-arg]
    except ValidationError as exc:
        raise AUTH_INDISPONIBLE from exc


def obtenir_cle(request: Request, jeton: Jeton) -> Any:
    """Clé publique du tenant qui a signé le jeton (``app.state.jwks``, créé au démarrage)."""
    if jeton is None:
        return None
    jwks = getattr(request.app.state, "jwks", None)
    if jwks is None:
        raise AUTH_INDISPONIBLE
    try:
        return jwks.get_signing_key_from_jwt(jeton.credentials).key
    except PyJWTError as exc:  # jeton mal formé, clé inconnue du tenant, JWKS injoignable
        raise ErreurApi(401, "JETON_INVALIDE", "Jeton invalide", NON_AUTHENTIFIE) from exc


def jeton_present(jeton: Jeton) -> HTTPAuthorizationCredentials:
    """Résolue en premier : sans jeton, 401 avant de lire la clé ou la configuration (pas 503)."""
    if jeton is None:
        raise ErreurApi(401, "JETON_ABSENT", "Jeton absent", NON_AUTHENTIFIE)
    return jeton


def exiger(role: Role) -> Callable[..., Appelant]:
    def dependance(
        jeton: Annotated[HTTPAuthorizationCredentials, Depends(jeton_present)],
        cle: Annotated[Any, Depends(obtenir_cle)],
        cfg: Annotated[ConfigAuth, Depends(charger_auth)],
    ) -> Appelant:
        try:
            appelant = verifier_jeton(jeton.credentials, cle, cfg)
        except ErreurAuth as exc:
            raise ErreurApi(401, "JETON_INVALIDE", "Jeton invalide", NON_AUTHENTIFIE) from exc
        if role not in appelant.roles:
            raise ErreurApi(403, "ROLE_MANQUANT", f"Rôle {role} requis")
        return appelant

    return dependance
