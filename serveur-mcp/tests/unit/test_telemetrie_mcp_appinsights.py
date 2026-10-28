"""TU — choix de l'exportateur : OTLP seul, ou App Insights en plus de l'OTLP (#54)."""

from __future__ import annotations

import os
from typing import Any

import pytest
from azure.monitor.opentelemetry._constants import _ALL_SUPPORTED_INSTRUMENTED_LIBRARIES
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from agentinsurflow_mcp.infrastructure.otel import telemetrie
from agentinsurflow_mcp.infrastructure.otel.telemetrie import (
    INSTRUMENTATIONS_DISTRO_COUPEES,
    configurer_telemetrie,
)

_CHAINE = "InstrumentationKey=00000000-0000-0000-0000-000000000000"
fournisseurs_poses: list[TracerProvider] = []


@pytest.fixture
def appels_azure(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    appels: list[dict[str, Any]] = []
    monkeypatch.setattr(
        telemetrie, "configure_azure_monitor", lambda **kw: appels.append(kw), raising=False
    )
    # le fournisseur global n'est jamais touché ; le dernier posé est gardé pour inspection
    fournisseurs_poses.clear()
    monkeypatch.setattr(telemetrie.trace, "set_tracer_provider", fournisseurs_poses.append)
    for cle in (
        "APPLICATIONINSIGHTS_CONNECTION_STRING",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "TELEMETRIE_AUDIENCE",
        "APP_ENV",
    ):
        monkeypatch.delenv(cle, raising=False)
    return appels


def test_otlp_seul_garde_le_comportement_actuel(appels_azure: list[dict[str, Any]]) -> None:
    configurer_telemetrie("t")
    assert appels_azure == []
    (fournisseur,) = fournisseurs_poses
    (proc,) = fournisseur._active_span_processor._span_processors  # type: ignore[attr-defined]
    assert isinstance(proc, BatchSpanProcessor)
    assert isinstance(proc.span_exporter, OTLPSpanExporter)


def test_app_insights_garde_l_otlp_en_processeur_supplementaire(
    monkeypatch: pytest.MonkeyPatch, appels_azure: list[dict[str, Any]]
) -> None:
    monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", _CHAINE)
    monkeypatch.setenv("OTEL_TRACES_SAMPLER", "")  # isole : restauré à la fin du test
    monkeypatch.delenv("OTEL_TRACES_SAMPLER")
    configurer_telemetrie("t")
    assert os.environ["OTEL_TRACES_SAMPLER"] == "parentbased_always_on"
    kw = appels_azure[0]
    (proc,) = kw["span_processors"]
    assert isinstance(proc.span_exporter, OTLPSpanExporter)
    assert kw["logger_name"] == "insurflow.audit"
    assert kw["enable_live_metrics"] is True
    assert kw["instrumentation_options"] == INSTRUMENTATIONS_DISTRO_COUPEES
    attrs = kw["resource"].attributes
    assert attrs["service.name"] == telemetrie.SERVICE
    assert attrs["deployment.environment"] == "local"


def test_toutes_les_instrumentations_du_distro_sont_coupees() -> None:
    assert INSTRUMENTATIONS_DISTRO_COUPEES.keys() == set(_ALL_SUPPORTED_INSTRUMENTED_LIBRARIES)
    assert {"httpx", "httpx2"} <= INSTRUMENTATIONS_DISTRO_COUPEES.keys()
    assert all(v == {"enabled": False} for v in INSTRUMENTATIONS_DISTRO_COUPEES.values())


def test_httpx_reste_non_instrumente(
    monkeypatch: pytest.MonkeyPatch, appels_azure: list[dict[str, Any]]
) -> None:
    monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", _CHAINE)
    configurer_telemetrie("t")
    assert appels_azure[0]["instrumentation_options"]["httpx"] == {"enabled": False}
