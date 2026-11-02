"""Traces en mémoire : les tests n'exportent jamais sur le réseau."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

_EXPORTATEUR = InMemorySpanExporter()


@pytest.fixture(scope="session", autouse=True)
def _fournisseur_de_traces() -> None:
    """Le SDK OTel, une fois par processus ; si un autre conftest l'a déjà posé, on s'y greffe."""
    fournisseur = trace.get_tracer_provider()
    if not isinstance(fournisseur, TracerProvider):
        fournisseur = TracerProvider()
        trace.set_tracer_provider(fournisseur)
    fournisseur.add_span_processor(SimpleSpanProcessor(_EXPORTATEUR))


@pytest.fixture
def spans() -> Iterator[InMemorySpanExporter]:
    _EXPORTATEUR.clear()
    yield _EXPORTATEUR
    _EXPORTATEUR.clear()
