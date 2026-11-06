"""Unitaires — span du client de calcul : aucune donnée du contrat (``httpx.MockTransport``)."""

from __future__ import annotations

import httpx
import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from agentinsurflow_mcp.infrastructure.fonction_calcul.client import ClientCalcul, ConfigCalcul


async def test_span_du_client_sans_donnee_du_contrat(
    spans: InMemorySpanExporter, monkeypatch: pytest.MonkeyPatch
) -> None:
    corps = {
        "version_bareme": "bareme-2026.10-v1",
        "decision": "ACCEPTE",
        "prime_ttc_annuelle": "819.73",
    }
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=corps))
    )
    monkeypatch.setattr(
        "agentinsurflow_mcp.infrastructure.fonction_calcul.client.credential_application",
        lambda *a: type("C", (), {"get_token": lambda s, p: type("J", (), {"token": "j"})()})(),
    )
    calc = ClientCalcul(http, ConfigCalcul(calcul_url="http://calcul", calcul_audience="api://c"))
    await calc.evaluer({"crm": "0.9"})
    (span,) = [s for s in spans.get_finished_spans() if s.name == "calcul.appeler"]
    attributs = dict(span.attributes or {})
    assert attributs["calcul.route"] == "/risques"
    assert attributs["http.status_code"] == 200
    assert attributs["resultat.code"] == "OK"
    assert attributs["bareme.version"] == "bareme-2026.10-v1"
    valeurs = " ".join(str(v) for v in attributs.values())
    for interdit in ("0.9", "819.73", "ACCEPTE"):
        assert interdit not in valeurs
