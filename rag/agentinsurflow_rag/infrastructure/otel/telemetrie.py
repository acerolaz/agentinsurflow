"""Traces OpenTelemetry de rag (spec §9) : exportées en OTLP/HTTP vers le référentiel SQL
d'underwriting-admin (``POST /v1/traces``, localhost dans la réplique : sans jeton, S3-21).

RGPD (G-02) : jamais le texte d'une question, un nom, une adresse ni un ``numero_contrat`` dans
un attribut ni un événement ; la question n'apparaît que par son sha256 et sa longueur. Les
clients httpx ne sont pas instrumentés (leur URL porterait le numéro de contrat) : le
``traceparent`` est injecté à la main. ``OTEL_SDK_DISABLED=true`` coupe tout (géré par le SDK).
"""

from __future__ import annotations

import os
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Span

SERVICE = "agentinsurflow-rag"
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


def url_sans_parametres(span: Span, scope: dict[str, Any]) -> None:
    """Crochet du span serveur : ``http.url`` sans la query string (``?question=…``)."""
    if span.is_recording():
        span.set_attribute("http.url", str(scope.get("path", "")))


def trace_id_courant() -> str | None:
    contexte = trace.get_current_span().get_span_context()
    return format(contexte.trace_id, "032x") if contexte.is_valid else None
