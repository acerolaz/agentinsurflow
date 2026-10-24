"""TU — spans du cluster : ``invoke_agent`` sans donnée personnelle, chemins HTTP anonymisés.

Un fournisseur local (jamais le global) : aucune interférence avec les autres services du dépôt.
"""

from __future__ import annotations

import logging

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from agentinsurflow_cluster.domain.models import Rapport
from agentinsurflow_cluster.domain.reglages import ReglageAgent
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


async def test_span_et_journal_portent_le_reglage_et_les_tokens(
    spans: InMemorySpanExporter, caplog: pytest.LogCaptureFixture
) -> None:
    rapport = Rapport("redacteur", {}, "llm", None, "v1", tokens_entree=30, tokens_sortie=12)
    reglage = ReglageAgent("gpt-4.1-mini", 0.2, 1200, 8.0, "redacteur.md")
    logging.getLogger("insurflow.audit").propagate = True
    with caplog.at_level(logging.INFO, logger="insurflow.audit"):
        await audit.AuditOtel().tracer("C-1", rapport, [], 10, reglage=reglage)
    (span,) = spans.get_finished_spans()
    attrs = dict(span.attributes or {})
    assert attrs["gen_ai.request.model"] == "gpt-4.1-mini"
    assert attrs["gen_ai.request.temperature"] == 0.2
    assert attrs["gen_ai.request.max_tokens"] == 1200
    assert attrs["gen_ai.usage.input_tokens"] == 30
    assert attrs["gen_ai.usage.output_tokens"] == 12
    (r,) = [r for r in caplog.records if r.name == "insurflow.audit"]
    assert (r.modele, r.temperature, r.max_tokens) == ("gpt-4.1-mini", 0.2, 1200)  # type: ignore[attr-defined]
    assert (r.tokens_entree, r.tokens_sortie) == (30, 12)  # type: ignore[attr-defined]
    assert "redacteur.md" not in str(vars(r))


async def test_span_de_la_saga_sans_reglage_n_a_aucun_attribut_de_requete(
    spans: InMemorySpanExporter,
) -> None:
    await audit.AuditOtel().tracer("C-1", Rapport("orchestrateur", {}, "llm", None, ""), [], 0)
    (span,) = spans.get_finished_spans()
    assert not [k for k in (span.attributes or {}) if k.startswith("gen_ai.request.")]


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
