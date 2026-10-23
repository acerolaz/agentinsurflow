"""Dépendance FastAPI : jeton Entra du gestionnaire (Bearer) et rôle ``Gestionnaire``."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClientConnectionError, PyJWTError

from ..infrastructure.entra.verification import ErreurAuth, Gestionnaire, verifier_jeton
from .problemes import Probleme

ROLE = "Gestionnaire"
NON_AUTHENTIFIE = {"WWW-Authenticate": "Bearer"}
_schema = HTTPBearer(auto_error=False)


async def gestionnaire_courant(
    request: Request,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_schema)],
) -> Gestionnaire:
    if creds is None or not creds.credentials:
        raise Probleme(401, "JETON_ABSENT", "Jeton absent", NON_AUTHENTIFIE)
    etat = request.app.state
    if etat.config is None or etat.jwks is None:
        raise Probleme(503, "AUTH_INDISPONIBLE", "Authentification Entra non configurée")
    try:
        # kid inconnu : le client JWKS interroge le réseau (appel bloquant)
        cle = (await asyncio.to_thread(etat.jwks.get_signing_key_from_jwt, creds.credentials)).key
        gestionnaire = verifier_jeton(creds.credentials, cle, etat.config)
    except PyJWKClientConnectionError as e:  # JWKS injoignable : pas la faute du jeton
        raise Probleme(503, "AUTH_INDISPONIBLE", "Authentification Entra indisponible") from e
    except (PyJWTError, ErreurAuth) as e:
        raise Probleme(401, "JETON_INVALIDE", "Jeton invalide", NON_AUTHENTIFIE) from e
    if ROLE not in gestionnaire.roles:
        raise Probleme(403, "ROLE_MANQUANT", f"Rôle {ROLE} requis")
    return gestionnaire
