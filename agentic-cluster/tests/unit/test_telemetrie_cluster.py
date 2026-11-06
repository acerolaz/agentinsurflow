"""TU — spans du cluster : ``invoke_agent`` sans donnée personnelle, chemins HTTP anonymisés.

Un fournisseur local (jamais le global) : aucune interférence avec les autres services du dépôt.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from azure.monitor.opentelemetry._constants import _ALL_SUPPORTED_INSTRUMENTED_LIBRARIES
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from agentinsurflow_cluster.domain.models import Rapport
from agentinsurflow_cluster.domain.reglages import ReglageAgent
from agentinsurflow_cluster.infrastructure.otel import audit, telemetrie
from agentinsurflow_cluster.infrastructure.otel.telemetrie import (
    INSTRUMENTATIONS_DISTRO_COUPEES,
    anonymiser_requete,
    configurer_telemetrie,
)

# le paquet api expose l'objet app sous ce nom : passer par le module
app_module = importlib.import_module("agentinsurflow_cluster.api.app")


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
    spans: InMemorySpanExporter,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rapport = Rapport("redacteur", {}, "llm", None, "v1", tokens_entree=30, tokens_sortie=12)
    reglage = ReglageAgent("gpt-4.1-mini", 0.2, 1200, 8.0, "redacteur.md")
    monkeypatch.setattr(logging.getLogger("insurflow.audit"), "propagate", True)
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
    await audit.AuditOtel().tracer("C-1", Rapport("saga", {}, "llm", None, ""), [], 0)
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


@pytest.mark.parametrize(
    ("methode", "suffixe"),
    [("POST", "/evaluation"), ("GET", "/evaluation"), ("PATCH", "/evaluation"),
     ("PUT", "/evaluation/decision")],
)  # fmt: skip
def test_le_numero_de_contrat_est_retire_des_attributs_http(methode: str, suffixe: str) -> None:
    span = _Span()
    chemin = f"/api/v1/souscriptions/AIF-2026-000042{suffixe}"
    anonymiser_requete(span, {"method": methode, "path": chemin})  # type: ignore[arg-type]
    attendu = f"/api/v1/souscriptions/{{numero_contrat}}{suffixe}"
    assert span.nom == f"{methode} {attendu}"
    assert set(span.attributs.values()) == {attendu}
    assert "000042" not in span.nom + "".join(span.attributs.values())


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
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "APP_ENV",
    ):
        monkeypatch.delenv(cle, raising=False)
    return appels


_CHAINE = "InstrumentationKey=00000000-0000-0000-0000-000000000000"


def test_sans_rien_aucun_export(appels_azure: list[dict[str, Any]]) -> None:
    configurer_telemetrie("t")
    assert appels_azure == []


def test_otlp_seul_garde_le_comportement_actuel(
    monkeypatch: pytest.MonkeyPatch, appels_azure: list[dict[str, Any]]
) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://x/v1/traces")
    configurer_telemetrie("t")
    assert appels_azure == []
    (fournisseur,) = fournisseurs_poses
    (proc,) = fournisseur._active_span_processor._span_processors  # type: ignore[attr-defined]
    assert isinstance(proc, BatchSpanProcessor)
    assert isinstance(proc.span_exporter, OTLPSpanExporter)


def test_app_insights_seul(
    monkeypatch: pytest.MonkeyPatch, appels_azure: list[dict[str, Any]]
) -> None:
    monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", _CHAINE)
    monkeypatch.delenv("OTEL_TRACES_SAMPLER", raising=False)
    configurer_telemetrie("t")
    assert os.environ["OTEL_TRACES_SAMPLER"] == "parentbased_always_on"
    kw = appels_azure[0]
    assert kw["span_processors"] == []
    assert kw["logger_name"] == "insurflow.audit"
    assert kw["enable_live_metrics"] is True
    assert kw["instrumentation_options"] == INSTRUMENTATIONS_DISTRO_COUPEES
    assert kw["resource"].attributes["deployment.environment"] == "local"


def test_double_export(monkeypatch: pytest.MonkeyPatch, appels_azure: list[dict[str, Any]]) -> None:
    monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", _CHAINE)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://x/v1/traces")
    configurer_telemetrie("t")
    (proc,) = appels_azure[0]["span_processors"]
    assert isinstance(proc.span_exporter, OTLPSpanExporter)


def test_toutes_les_instrumentations_du_distro_sont_coupees() -> None:
    assert INSTRUMENTATIONS_DISTRO_COUPEES.keys() == set(_ALL_SUPPORTED_INSTRUMENTED_LIBRARIES)
    assert {"httpx", "httpx2"} <= INSTRUMENTATIONS_DISTRO_COUPEES.keys()
    assert all(v == {"enabled": False} for v in INSTRUMENTATIONS_DISTRO_COUPEES.values())


def test_ligne_audit_evaluation_sans_donnee_personnelle(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(logging.getLogger("insurflow.audit"), "propagate", True)
    with caplog.at_level(logging.INFO, logger="insurflow.audit"):
        asyncio.run(
            audit.AuditOtel().evaluation("AIF-2026-000001", "REVUE_HUMAINE", "llm_ko", 9876)
        )
    (enreg,) = [r for r in caplog.records if r.name == "insurflow.audit"]
    ligne = json.loads(audit.FormatJson().format(enreg))
    assert ligne["message"] == "audit.evaluation"
    assert (ligne["numero_contrat"], ligne["statut_final"]) == ("AIF-2026-000001", "REVUE_HUMAINE")
    assert (ligne["cause"], ligne["duree_ms"]) == ("llm_ko", 9876)
    assert set(ligne) <= {"message", *audit.CHAMPS}


def test_chargement_des_garde_fous_journalise(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(logging.getLogger("insurflow.audit"), "propagate", True)
    with caplog.at_level(logging.INFO, logger="insurflow.audit"):
        audit.journaliser_chargement_garde_fous(6123)
    (enreg,) = [r for r in caplog.records if r.name == "insurflow.audit"]
    ligne = json.loads(audit.FormatJson().format(enreg))
    assert (ligne["message"], ligne["chargement_ms"]) == ("garde_fous.chargement", 6123)


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


@pytest.fixture
def journal_vierge() -> Any:
    """Le journal d'audit tel qu'au démarrage d'un processus, restauré ensuite."""
    journal = logging.getLogger("insurflow.audit")
    etat = (journal.handlers[:], journal.level, journal.propagate)

    for h in journal.handlers[:]:
        journal.removeHandler(h)
    journal.setLevel(logging.NOTSET)
    journal.propagate = True

    yield journal

    for h in journal.handlers[:]:
        journal.removeHandler(h)
    for h in etat[0]:
        journal.addHandler(h)
    journal.setLevel(etat[1])
    journal.propagate = etat[2]


def test_audit_info_emis_quand_azure_a_deja_pose_son_gestionnaire(journal_vierge: Any) -> None:
    # #176 : configure_azure_monitor(logger_name=…) ajoute son gestionnaire avant ce réglage
    azure = _Capture()
    journal_vierge.addHandler(azure)
    audit.configurer_journal_audit()
    audit.journaliser_chargement_garde_fous(1)
    assert azure.messages == ["garde_fous.chargement"]
    sortie = [h for h in journal_vierge.handlers if isinstance(h.formatter, audit.FormatJson)]
    assert len(sortie) == 1  # et la ligne JSON part aussi sur la sortie standard


def test_configurer_le_journal_deux_fois_ne_double_pas_les_lignes(journal_vierge: Any) -> None:
    audit.configurer_journal_audit()
    audit.configurer_journal_audit()
    assert len(journal_vierge.handlers) == 1


async def test_le_demarrage_du_serveur_configure_la_telemetrie_avant_le_journal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    appels: list[str] = []
    monkeypatch.setattr(app_module, "configurer_telemetrie", lambda _v: appels.append("telemetrie"))
    monkeypatch.setattr(app_module, "configurer_journal_audit", lambda: appels.append("journal"))
    monkeypatch.delenv("AZURE_TENANT_ID", raising=False)

    @asynccontextmanager
    async def composition(_config: Any) -> AsyncIterator[Any]:
        yield object()

    app = app_module.creer_app(composition)
    async with app.router.lifespan_context(app):
        assert appels == ["telemetrie", "journal"]
