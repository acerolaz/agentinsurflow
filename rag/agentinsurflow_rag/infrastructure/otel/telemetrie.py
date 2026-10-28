"""Traces OpenTelemetry de rag (spec §9) : exportées en OTLP/HTTP vers le référentiel SQL
d'underwriting-admin (``POST /v1/traces``). Local : direct, sans jeton ; Azure : par la gateway
avec un jeton d'application (rôle ``Telemetrie``, audience ``TELEMETRIE_AUDIENCE``).

RGPD (G-02) : jamais le texte d'une question, un nom, une adresse ni un ``numero_contrat`` dans
un attribut ni un événement ; la question n'apparaît que par son sha256 et sa longueur. Les
clients httpx ne sont pas instrumentés (leur URL porterait le numéro de contrat) : le
``traceparent`` est injecté à la main. ``OTEL_SDK_DISABLED=true`` coupe tout (géré par le SDK).
"""

from __future__ import annotations

import logging
import os
from typing import Any

import requests  # transitif via l'exportateur OTLP/HTTP, comme le serveur MCP (non déclaré)
from azure.core.exceptions import AzureError
from azure.monitor.opentelemetry import configure_azure_monitor
from azure.monitor.opentelemetry._constants import _ALL_SUPPORTED_INSTRUMENTED_LIBRARIES
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Span
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from ..entra.application import credential_application

SERVICE = "agentinsurflow-rag"
POINT_OTLP = "http://localhost:8002/v1/traces"

journal = logging.getLogger(__name__)
tracer = trace.get_tracer("agentinsurflow")
# Le distro active ses instrumentations par défaut : on les coupe toutes, ce service garde les
# siennes ; httpx reste non instrumenté (son URL porterait le numéro de contrat).
# Liste dérivée du distro (import privé accepté : version épinglée ==1.8.11), pour ne rien oublier.
INSTRUMENTATIONS_DISTRO_COUPEES: dict[str, dict[str, bool]] = {
    nom: {"enabled": False} for nom in _ALL_SUPPORTED_INSTRUMENTED_LIBRARIES
}


class ConfigTelemetrie(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    telemetrie_audience: str | None = None  # api://<appId underwriting> : absent = sans jeton
    azure_tenant_id: str | None = None
    rag_api_client_id: str | None = None
    rag_client_secret: SecretStr | None = None
    azure_uami_client_id: str | None = None


def session_authentifiee(credential: Any, audience: str) -> requests.Session:
    """Session dont ``auth`` pose le jeton d'application (rôle ``Telemetrie``) à chaque export."""
    portee = f"{audience}/.default"

    def poser(requete: requests.PreparedRequest) -> requests.PreparedRequest:
        try:
            requete.headers["Authorization"] = f"Bearer {credential.get_token(portee).token}"
        except AzureError:
            # ponytail: sans jeton l'export part en 401 (spans perdus), jamais de blocage
            journal.warning("jeton de télémétrie indisponible")
        return requete

    session = requests.Session()
    session.auth = poser
    return session


def creer_exportateur(point: str) -> OTLPSpanExporter:
    cfg = ConfigTelemetrie()
    if cfg.telemetrie_audience:
        secret = cfg.rag_client_secret.get_secret_value() if cfg.rag_client_secret else None
        cred = credential_application(
            cfg.azure_tenant_id, cfg.rag_api_client_id, secret, cfg.azure_uami_client_id
        )
        if cred is not None:
            return OTLPSpanExporter(
                endpoint=point, session=session_authentifiee(cred, cfg.telemetrie_audience)
            )
    return OTLPSpanExporter(endpoint=point)


def configurer_telemetrie(version: str) -> None:
    """Une fois par processus (convention du SDK)."""
    os.environ.setdefault(
        "OTEL_TRACES_SAMPLER", "parentbased_always_on"
    )  # 100 % des traces (référentiel SQL complet, D-V2)
    ressource = Resource.create(
        {
            "service.name": SERVICE,
            "service.version": version,
            "deployment.environment": os.environ.get("APP_ENV", "local"),
        }
    )
    point = os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", POINT_OTLP)
    # ponytail: une perte des spans (underwriting-admin en panne) ne bloque jamais une réponse
    otlp = BatchSpanProcessor(creer_exportateur(point))
    if os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        # le distro pose le fournisseur global ; la chaîne est lue par lui dans l'environnement.
        # L'OTLP vers underwriting-admin reste, en processeur de spans supplémentaire (#54).
        configure_azure_monitor(
            resource=ressource,
            span_processors=[otlp],
            logger_name="insurflow.audit",
            enable_live_metrics=True,
            instrumentation_options=INSTRUMENTATIONS_DISTRO_COUPEES,
        )
        return
    fournisseur = TracerProvider(resource=ressource)
    fournisseur.add_span_processor(otlp)
    trace.set_tracer_provider(fournisseur)


def url_sans_parametres(span: Span, scope: dict[str, Any]) -> None:
    """Crochet du span serveur : ``http.url`` sans la query string (``?question=…``)."""
    if span.is_recording():
        span.set_attribute("http.url", str(scope.get("path", "")))


def trace_id_courant() -> str | None:
    contexte = trace.get_current_span().get_span_context()
    return format(contexte.trace_id, "032x") if contexte.is_valid else None
