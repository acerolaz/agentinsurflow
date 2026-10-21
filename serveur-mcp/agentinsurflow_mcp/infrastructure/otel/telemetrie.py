"""Traces OpenTelemetry du serveur MCP (spec § 7) : exportées en OTLP/HTTP vers le référentiel SQL
d'underwriting-admin (``POST /v1/traces``, localhost dans la réplique : sans jeton).

RGPD : jamais le texte d'une question, un ``numero_contrat``, un jeton ni un ``oid`` dans un
attribut ni un événement ; la question n'apparaît que par son sha256 et sa longueur, la route
HTTP que par son gabarit. Le client httpx n'est pas instrumenté (son URL porterait le numéro de
contrat) : le ``traceparent`` est injecté à la main. ``OTEL_SDK_DISABLED=true`` coupe tout
(géré par le SDK).
"""

from __future__ import annotations

import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

SERVICE = "agentinsurflow-mcp"
POINT_OTLP = "http://localhost:8002/v1/traces"

tracer = trace.get_tracer("agentinsurflow")


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
    fournisseur.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=point)))
    trace.set_tracer_provider(fournisseur)
