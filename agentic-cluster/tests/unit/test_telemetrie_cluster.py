"""TU — spans du cluster : ``invoke_agent`` sans donnée personnelle, chemins HTTP anonymisés.

Un fournisseur local (jamais le global) : aucune interférence avec les autres services du dépôt.
"""

from __future__ import annotations

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from agentinsurflow_cluster.domain.models import Rapport
from agentinsurflow_cluster.infrastructure.otel import audit
from agentinsurflow_cluster.infrastructure.otel.telemetrie import anonymiser_requete


@pytest.fixture
def spans(monkeypatch: pytest.MonkeyPatch) -> InMemorySpanExporter:
    exportateur = InMemorySpanExporter()
    fournisseur = TracerProvider()
    fournisseur.add_span_processor(SimpleSpanProcessor(exportateur))
    monkeypatch.setattr(audit, "tracer", fournisseur.get_tracer("test"))
    return exportateur


async def test_span_invoke_agent_porte_l_agent_le_mode_et_la_cause_seulement(
    spans: InMemorySpanExporter,
) -> None:
    rapport = Rapport("redacteur", {}, "repli", "garde_fou:GF3", "v1")
    await audit.AuditOtel().tracer("C-SECRET", rapport, ["GF3"], 1500, "ab" * 32)
    (span,) = spans.get_finished_spans()
    assert span.name == "invoke_agent"
    assert dict(span.attributes or {}) == {
        "gen_ai.agent.name": "redacteur",
        "insurflow.mode": "repli",
        "insurflow.cause": "garde_fou:GF3",
    }
    assert (span.end_time or 0) - (span.start_time or 0) == 1_500_000_000
    assert "C-SECRET" not in str(span.attributes)


class _Span:
    def __init__(self) -> None:
        self.nom = ""
        self.attributs: dict[str, str] = {}

    def is_recording(self) -> bool:
        return True

    def update_name(self, nom: str) -> None:
        self.nom = nom

    def set_attribute(self, cle: str, valeur: str) -> None:
        self.attributs[cle] = valeur


def test_le_numero_de_contrat_est_retire_des_attributs_http() -> None:
    span = _Span()
    anonymiser_requete(span, {"method": "POST", "path": "/evaluations/C-SECRET/revue"})  # type: ignore[arg-type]
    assert span.nom == "POST /evaluations/{numero_contrat}/revue"
    assert set(span.attributs.values()) == {"/evaluations/{numero_contrat}/revue"}
