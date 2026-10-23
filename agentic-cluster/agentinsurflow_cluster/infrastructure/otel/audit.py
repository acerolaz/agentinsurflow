"""Audit des agents (R14) : un enregistrement ``audit.agent`` par exécution, plus un span.

Journal ``insurflow.audit`` (stdlib) : jamais de jeton, de contenu de prompt ni d'observations ;
la vue et le rapport n'apparaissent que par leur empreinte SHA-256.
"""

from __future__ import annotations

import json
import logging
import time

from opentelemetry import trace

from agentinsurflow_cluster.application.agents import empreinte
from agentinsurflow_cluster.application.serialisation import vers_json
from agentinsurflow_cluster.domain.models import Rapport

journal = logging.getLogger("insurflow.audit")
tracer = trace.get_tracer("agentinsurflow")
CHAMPS = (
    "trace_id", "numero_contrat", "agent", "mode", "cause", "version_prompt", "garde_fous",
    "vue_sha256", "rapport_sha256", "duree_ms", "signal_injection",
)  # fmt: skip


class FormatJson(logging.Formatter):
    """Une ligne JSON par enregistrement d'audit."""

    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {"message": record.getMessage(), **{c: getattr(record, c, None) for c in CHAMPS}},
            ensure_ascii=False,
        )


def configurer_journal_audit() -> None:
    if not journal.handlers:
        gestionnaire = logging.StreamHandler()
        gestionnaire.setFormatter(FormatJson())
        journal.addHandler(gestionnaire)
        journal.setLevel(logging.INFO)
        journal.propagate = False


class AuditOtel:
    """Adapter de ``AuditPort``."""

    async def tracer(
        self,
        numero_contrat: str,
        rapport: Rapport,
        garde_fous: list[str],
        duree_ms: int,
        empreinte_vue: str = "",
        signal_injection: float | None = None,
    ) -> None:
        fin = time.time_ns()
        span = tracer.start_span(
            "invoke_agent",
            start_time=fin - duree_ms * 1_000_000,
            attributes={
                "gen_ai.agent.name": rapport.agent,
                "insurflow.mode": rapport.mode,
                "insurflow.cause": rapport.cause or "",
                **(
                    {"insurflow.signal_injection": signal_injection}
                    if signal_injection is not None
                    else {}
                ),
            },
        )
        span.end(end_time=fin)
        contexte = span.get_span_context()
        trace_id = format(contexte.trace_id, "032x") if contexte.is_valid else ""
        journal.info(
            "audit.agent",
            extra={
                "trace_id": trace_id,
                "numero_contrat": numero_contrat,
                "agent": rapport.agent,
                "mode": rapport.mode,
                "cause": rapport.cause,
                "version_prompt": rapport.version_prompt,
                "garde_fous": garde_fous,
                "vue_sha256": empreinte_vue,
                "rapport_sha256": empreinte(vers_json(rapport.section)),
                "duree_ms": duree_ms,
                "signal_injection": signal_injection,
            },
        )
