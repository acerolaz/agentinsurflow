"""Traces OpenTelemetry du cluster (R14) : exportateur OTLP configuré par l'environnement.

``OTEL_SERVICE_NAME`` (``agentic-cluster``), ``OTEL_EXPORTER_OTLP_*`` et ``OTEL_SDK_DISABLED`` sont
lus par le SDK. Sans point de terminaison, les spans restent locaux (aucun export). Application
Insights viendra avec le ticket #54.

RGPD : jamais de nom, d'e-mail, de jeton, de contenu de prompt ni de texte d'observations dans un
attribut ; le numéro de contrat est retiré des chemins HTTP (gabarit seulement).
"""

from __future__ import annotations

import os
import re
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.propagate import inject
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Span

SERVICE = "agentic-cluster"
_NUMERO = re.compile(r"/evaluations/[^/?]+")


def configurer_telemetrie(version: str) -> None:
    """Une fois par processus (convention du SDK)."""
    os.environ.setdefault("OTEL_SERVICE_NAME", SERVICE)
    fournisseur = TracerProvider(
        resource=Resource.create(
            {
                "service.version": version,
                "deployment.environment": os.environ.get("APP_ENV", "local"),
            }
        )
    )
    if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or os.environ.get(
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"
    ):
        # ponytail: une perte de spans (collecteur en panne) ne bloque jamais une réponse
        fournisseur.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(fournisseur)


def trace_id_courant() -> str:
    """Identifiant de la trace courante en hexadécimal, ou ``""`` hors span."""
    contexte = trace.get_current_span().get_span_context()
    return format(contexte.trace_id, "032x") if contexte.is_valid else ""


def traceparent_courant() -> str | None:
    entetes: dict[str, str] = {}
    inject(entetes)
    return entetes.get("traceparent")


def anonymiser_requete(span: Span, scope: dict[str, Any]) -> None:
    """Hook de l'instrumentation ASGI : le numéro de contrat ne reste dans aucun attribut."""
    if not span.is_recording():
        return
    chemin = _NUMERO.sub("/evaluations/{numero_contrat}", scope.get("path", ""))
    span.update_name(f"{scope.get('method', '')} {chemin}".strip())
    for cle in ("url.path", "http.target", "url.full", "http.url"):
        span.set_attribute(cle, chemin)
