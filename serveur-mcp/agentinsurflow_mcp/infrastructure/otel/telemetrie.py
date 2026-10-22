"""Traces OpenTelemetry du serveur MCP (spec § 7) : exportées en OTLP/HTTP vers le référentiel SQL
d'underwriting-admin (``POST /v1/traces``, localhost dans la réplique : sans jeton).

RGPD : jamais le texte d'une question, un ``numero_contrat``, un jeton ni un ``oid`` dans un
attribut ni un événement ; la question n'apparaît que par son sha256 et sa longueur, la route
HTTP que par son gabarit. Le client httpx n'est pas instrumenté (son URL porterait le numéro de
contrat) : le ``traceparent`` est injecté à la main. ``OTEL_SDK_DISABLED=true`` coupe tout
(géré par le SDK).
"""

from __future__ import annotations

import logging
import os
from typing import Any

import requests
from azure.core.exceptions import AzureError
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Span, Status, StatusCode
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from ..entra.application import credential_application

SERVICE = "agentinsurflow-mcp"
POINT_OTLP = "http://localhost:8002/v1/traces"

journal = logging.getLogger(__name__)
tracer = trace.get_tracer("agentinsurflow")


class ConfigTelemetrie(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    telemetrie_audience: str | None = None  # api://<appId underwriting> : absent = sans jeton
    azure_tenant_id: str | None = None
    mcp_api_client_id: str | None = None
    mcp_client_secret: SecretStr | None = None
    azure_uami_client_id: str | None = None


def session_authentifiee(credential: Any, audience: str) -> requests.Session:
    """Session dont ``auth`` pose le jeton d'application (rôle ``Telemetrie``) à chaque export."""
    portee = f"{audience}/.default"

    def poser(requete: requests.PreparedRequest) -> requests.PreparedRequest:
        try:
            requete.headers["Authorization"] = f"Bearer {credential.get_token(portee).token}"
        except AzureError as exc:
            # ponytail: sans jeton l'export part en 401 (spans perdus), jamais de blocage
            journal.warning("jeton de télémétrie indisponible (%s)", type(exc).__name__)
        return requete

    session = requests.Session()
    session.auth = poser
    return session


def creer_exportateur(point: str) -> OTLPSpanExporter:
    cfg = ConfigTelemetrie()
    if cfg.telemetrie_audience:
        secret = cfg.mcp_client_secret.get_secret_value() if cfg.mcp_client_secret else None
        cred = credential_application(
            cfg.azure_tenant_id, cfg.mcp_api_client_id, secret, cfg.azure_uami_client_id
        )
        if cred is not None:
            session = session_authentifiee(cred, cfg.telemetrie_audience)
            return OTLPSpanExporter(endpoint=point, session=session)
    return OTLPSpanExporter(endpoint=point)


def configurer_telemetrie(version: str) -> None:
    """Une fois par processus (convention du SDK)."""
    fournisseur = TracerProvider(
        resource=Resource.create(
            {
                "service.name": SERVICE,
                "service.version": version,
                "deployment.environment": os.environ.get("APP_ENV", "local"),
            }
        )
    )
    point = os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", POINT_OTLP)
    # ponytail: une perte des spans (underwriting-admin en panne) ne bloque jamais une réponse
    fournisseur.add_span_processor(BatchSpanProcessor(creer_exportateur(point)))
    trace.set_tracer_provider(fournisseur)


def echec(span: Span, message: str) -> None:
    """Statut ERROR à message constant : jamais ``str(exc)`` (il peut porter une valeur saisie)."""
    span.set_status(Status(StatusCode.ERROR, message))
