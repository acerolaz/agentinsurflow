"""Traces OpenTelemetry de rag (spec §9) : exportées en OTLP/HTTP vers le référentiel SQL
d'underwriting-admin (``POST /v1/traces``, localhost dans la réplique : sans jeton, S3-21).

RGPD (G-02) : jamais le texte d'une question, un nom, une adresse ni un ``numero_contrat`` dans
un attribut ; la question n'apparaît que par son sha256 et sa longueur.
"""

from __future__ import annotations

import hashlib
import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

SERVICE = "agentinsurflow-rag"
POINT_OTLP = "http://localhost:8002/v1/traces"

tracer = trace.get_tracer("agentinsurflow")


def configurer_telemetrie(version: str) -> TracerProvider | None:
    """Une fois par processus (convention du SDK) ; ``OTEL_SDK_DISABLED=true`` la coupe."""
    if os.environ.get("OTEL_SDK_DISABLED", "").lower() == "true":
        return None
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
    HTTPXClientInstrumentor().instrument()
    return fournisseur


def empreinte(texte: str) -> str:
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


def trace_id_courant() -> str | None:
    contexte = trace.get_current_span().get_span_context()
    return format(contexte.trace_id, "032x") if contexte.is_valid else None
