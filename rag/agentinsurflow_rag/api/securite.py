"""Authentification des routes de rag : jeton Entra (Bearer) et rôle d'app, refus par défaut.

Chaque route protégée déclare ``Depends(exiger("<rôle>"))`` ; sans cette déclaration, une route
ne lit rien du corpus (aucune connexion n'est fournie hors de ces dépendances).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any, Literal

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClientError

from ..domain.models import Appelant
from ..infrastructure.entra.jetons import ConfigAuth, ErreurAuth, verifier_jeton
from .erreurs import ErreurApi

Role = Literal["Gestionnaire", "Ingestion"]

bearer = HTTPBearer(auto_error=False, scheme_name="entra", description="Jeton Entra ID")
Jeton = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]

NON_AUTHENTIFIE = {"WWW-Authenticate": "Bearer"}


def charger_auth() -> ConfigAuth:
    return ConfigAuth()  # type: ignore[call-arg]


def obtenir_cle(request: Request, jeton: Jeton) -> Any:
    """Clé publique du tenant qui a signé le jeton (``app.state.jwks``, créé au démarrage)."""
    if jeton is None:
        return None
    try:
        return request.app.state.jwks.get_signing_key_from_jwt(jeton.credentials).key
    except PyJWKClientError as exc:
        raise ErreurApi(401, "JETON_INVALIDE", "Jeton invalide", NON_AUTHENTIFIE) from exc


def exiger(role: Role) -> Callable[..., Appelant]:
    def dependance(
        jeton: Jeton,
        cle: Annotated[Any, Depends(obtenir_cle)],
        cfg: Annotated[ConfigAuth, Depends(charger_auth)],
    ) -> Appelant:
        if jeton is None:
            raise ErreurApi(401, "JETON_ABSENT", "Jeton absent", NON_AUTHENTIFIE)
        try:
            appelant = verifier_jeton(jeton.credentials, cle, cfg)
        except ErreurAuth as exc:
            raise ErreurApi(401, "JETON_INVALIDE", "Jeton invalide", NON_AUTHENTIFIE) from exc
        if role not in appelant.roles:
            raise ErreurApi(403, "ROLE_MANQUANT", f"Rôle {role} requis")
        return appelant

    return dependance
