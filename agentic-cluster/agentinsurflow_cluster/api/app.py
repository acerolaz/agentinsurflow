"""Application HTTP du cluster : ``/health`` et ``/evaluations`` (port 8004, jeton Entra exigé)."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from importlib.metadata import version
from typing import Any

from fastapi import FastAPI
from jwt import PyJWKClient
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from ..application.agents import Dependances
from ..domain.models import NomAgent
from ..domain.reglages import ReglageAgent
from ..infrastructure.entra.config import ConfigCluster
from ..infrastructure.entra.obo import JetonsAgents
from ..infrastructure.entra.verification import url_jwks
from ..infrastructure.garde_fous.llm_guard import ScannersLlmGuard
from ..infrastructure.langgraph.checkpoint import checkpointer
from ..infrastructure.langgraph.graphe import ServiceEvaluation
from ..infrastructure.llm.fabrique import RedactionLangChain, version_prompt
from ..infrastructure.llm.modele import modele_chat
from ..infrastructure.llm.reglages import charger_reglages
from ..infrastructure.mcp.client import ClientMcpGateway
from ..infrastructure.otel.audit import (
    AuditOtel,
    configurer_journal_audit,
    journaliser_chargement_garde_fous,
)
from ..infrastructure.otel.telemetrie import (
    anonymiser_requete,
    configurer_telemetrie,
    trace_id_courant,
    traceparent_courant,
)
from . import problemes
from .routes import routeur

journal = logging.getLogger(__name__)
Composition = Callable[[ConfigCluster], AbstractAsyncContextManager[ServiceEvaluation]]


def composition_reelle(cfg: ConfigCluster) -> AbstractAsyncContextManager[ServiceEvaluation]:
    """Lit et valide `agents.toml` tout de suite (``ReglageInvalide`` arrête le démarrage)."""
    budget_global_s = float(os.environ.get("INSURFLOW_BUDGET_S") or 25)
    return _assembler(cfg, charger_reglages(budget_global_s), budget_global_s)


@asynccontextmanager
async def _assembler(
    cfg: ConfigCluster, reglages: dict[NomAgent, ReglageAgent], budget_global_s: float
) -> AsyncIterator[ServiceEvaluation]:
    """Adapters réels ; les scanners (modèles Hugging Face) se chargent dans un thread."""
    jetons = JetonsAgents(cfg)
    client = ClientMcpGateway(cfg.gateway_url, jetons, traceparent_courant)
    debut = time.perf_counter()
    garde = await asyncio.to_thread(ScannersLlmGuard)
    journaliser_chargement_garde_fous(int((time.perf_counter() - debut) * 1000))
    deps = Dependances(
        outils=client,
        redaction=RedactionLangChain(
            lambda nom: modele_chat(reglages[nom], nom, cfg, jetons), client, reglages
        ),
        garde=garde,
        audit=AuditOtel(),
        reglages=reglages,
        pieces_exigees=cfg.pieces_exigees(),
        versions_prompt={a: version_prompt(g.prompt) for a, g in reglages.items()},
        trace_id=trace_id_courant,
        budget_global_s=budget_global_s,
        reserve_s=float(os.environ.get("INSURFLOW_RESERVE_S") or 2),
    )
    async with checkpointer(cfg, budget_global_s) as saver:
        yield ServiceEvaluation(deps, saver)


# Chemins publics de la gateway (T12) : la page Swagger unique appelle la gateway, pas le cluster.
CHEMINS_PUBLICS = {
    "/evaluations/{numero_contrat}": "/v1/souscriptions/{numero_contrat}/evaluation",
    "/evaluations/{numero_contrat}/revue": "/v1/souscriptions/{numero_contrat}/revue",
    "/evaluations/{numero_contrat}/pause": "/v1/souscriptions/{numero_contrat}/pause",
    "/health": "/health/cluster",
}


def creer_app(composition: Composition = composition_reelle) -> FastAPI:
    async def preparer(
        app: FastAPI, contexte: AbstractAsyncContextManager[ServiceEvaluation]
    ) -> None:
        # tâche de fond : /health répond 503 tant que les modèles ne sont pas chargés
        try:
            async with contexte as service:
                app.state.service = service
                await app.state.arret.wait()
        except Exception:  # noqa: BLE001 - la sonde reste en 503, la cause va au journal
            journal.exception("démarrage du cluster impossible")

    @asynccontextmanager
    async def cycle_de_vie(app: FastAPI) -> AsyncIterator[None]:
        if app.state.config is None:  # déjà posée : tests (qui posent aussi leur JWKS)
            configurer_telemetrie(app.state.version)
            configurer_journal_audit()
            app.state.config = ConfigCluster()
            if app.state.config.azure_tenant_id:
                app.state.jwks = PyJWKClient(url_jwks(app.state.config), cache_keys=True)
            else:  # ponytail: l'API démarre quand même, les routes répondent 503
                journal.warning("Entra non configuré (AZURE_TENANT_ID) : 503")
        app.state.arret = asyncio.Event()
        # la composition valide le réglage à l'appel : une erreur arrête le démarrage
        contexte = composition(app.state.config)
        app.state.tache = asyncio.create_task(preparer(app, contexte))
        try:
            yield
        finally:
            app.state.arret.set()
            await app.state.tache

    app = FastAPI(
        title="AgentInsurFlow — cluster d'agents",
        version=os.environ.get("APP_VERSION") or version("agentinsurflow-cluster"),
        lifespan=cycle_de_vie,
        # seul l'instrumenteur ci-dessous est actif ; /health n'est pas tracé (sondes)
        telemetry={"tracing": False, "metrics": False, "logs": False, "operation_spans": False},
    )
    app.state.version = os.environ.get("APP_VERSION") or "dev"
    app.state.config = None
    app.state.jwks = None
    app.state.service = None
    schema_interne = app.openapi

    def openapi_public() -> dict[str, Any]:
        schema = schema_interne()  # mis en cache par FastAPI : le renommage est idempotent
        schema["paths"] = {CHEMINS_PUBLICS.get(c, c): v for c, v in schema["paths"].items()}
        return schema

    app.openapi = openapi_public  # type: ignore[method-assign]
    problemes.installer(app)
    app.include_router(routeur)
    FastAPIInstrumentor.instrument_app(
        app, excluded_urls="health", server_request_hook=anonymiser_requete
    )
    return app


app = creer_app()
