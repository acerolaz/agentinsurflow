"""Traces OpenTelemetry du cluster (R14) : exportateur OTLP configuré par l'environnement.

``OTEL_SERVICE_NAME`` (``agentic-cluster``), ``OTEL_EXPORTER_OTLP_*`` et ``OTEL_SDK_DISABLED`` sont
lus par le SDK. Sans point de terminaison, les spans restent locaux (aucun export). Application
Insights viendra avec le ticket #54.

Azure (``TELEMETRIE_AUDIENCE`` posée) : comme le serveur MCP, export par la gateway (``/v1/traces``)
avec un jeton d'application de l'inscription du cluster (assertion fédérée de l'identité managée),
rôle ``Telemetrie`` d'underwriting-admin. Local : export direct sans jeton.

RGPD : jamais de nom, d'e-mail, de jeton, de contenu de prompt ni de texte d'observations dans un
attribut ; le numéro de contrat est retiré des chemins HTTP (gabarit seulement).
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import requests
from azure.core.exceptions import AzureError
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.propagate import inject
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Span

from ..entra.config import ConfigCluster
from ..entra.jetons import credential_application, source_assertion

journal = logging.getLogger(__name__)
SERVICE = "agentic-cluster"
_NUMERO = re.compile(r"/evaluations/[^/?]+")


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


def creer_exportateur() -> OTLPSpanExporter:
    cfg = ConfigCluster()
    if cfg.telemetrie_audience and cfg.azure_tenant_id and cfg.insurflow_cluster_client_id:
        assertion = source_assertion(cfg)
        if assertion is not None:
            cred = credential_application(
                cfg.azure_tenant_id, cfg.insurflow_cluster_client_id, assertion
            )
            return OTLPSpanExporter(session=session_authentifiee(cred, cfg.telemetrie_audience))
    return OTLPSpanExporter()


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
        fournisseur.add_span_processor(BatchSpanProcessor(creer_exportateur()))
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
