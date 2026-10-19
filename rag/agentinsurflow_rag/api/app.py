"""API REST de rag ; Swagger UI sur ``/``.

Ressources : ``/health``, ``/api/reponses``, ``/api/ingestions``, ``/api/extraits``,
``/api/documents/{doc_id}``. Routes minces : HTTP → cas d'usage → DTO Pydantic.
Derrière la gateway, le document est servi en ``/rag/openapi.json`` dans la page Swagger unique ;
il ne déclare pas de ``servers`` : le « Try it out » vise les routes publiques de la gateway.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version

from fastapi import FastAPI
from jwt import PyJWKClient
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from pydantic import ValidationError

from ..infrastructure.entra.jetons import ConfigAuth
from ..infrastructure.otel.telemetrie import configurer_telemetrie
from ..infrastructure.postgres.connexions import ConfigBD, creer_moteurs
from .erreurs import installer_gestionnaires
from .routes import agent, corpus, sante

journal = logging.getLogger(__name__)


VERSION = version("agentinsurflow-rag")


@asynccontextmanager
async def cycle_de_vie(app: FastAPI) -> AsyncIterator[None]:
    configurer_telemetrie(VERSION)
    # ponytail: sans configuration, l'API démarre quand même (le déploiement actuel n'a pas encore
    # de PostgreSQL ni d'inscription Entra) ; les routes concernées répondent 503
    try:
        app.state.moteurs = creer_moteurs(ConfigBD())  # type: ignore[call-arg]
    except ValidationError:
        journal.warning("PostgreSQL non configuré (PG_*) : routes du corpus en 503")
        app.state.moteurs = None
    try:
        app.state.jwks = PyJWKClient(ConfigAuth().url_jwks, cache_keys=True)  # type: ignore[call-arg]
    except ValidationError:
        journal.warning("Entra non configuré (AZURE_TENANT_ID, RAG_API_CLIENT_ID) : jetons en 503")
        app.state.jwks = None
    yield
    if app.state.moteurs is not None:
        await app.state.moteurs.fermer()


app = FastAPI(
    title="AgentInsurFlow — rag",
    version=VERSION,
    docs_url="/",
    lifespan=cycle_de_vie,
)
installer_gestionnaires(app)
app.include_router(sante.router)
app.include_router(agent.router)
app.include_router(corpus.router)
# span serveur par requête (méthode, route, statut) ; /health n'est pas tracé (sondes)
FastAPIInstrumentor.instrument_app(app, excluded_urls="health")
