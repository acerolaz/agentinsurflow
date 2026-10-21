"""TI — traces OTLP du serveur MCP : spans, propagation, aucune donnée personnelle (RGPD)."""

from __future__ import annotations

import hashlib
from typing import Any

import httpx
import pytest
from jetons_mcp_de_test import AZP_ORCHESTRATEUR, AZP_REDACTEUR, config_auth, creer
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from session_mcp import FauxJwks, session_mcp

from agentinsurflow_mcp.api.app import creer_app
from agentinsurflow_mcp.api.serveur import ServeurMcp
from agentinsurflow_mcp.infrastructure.entra import obo
from agentinsurflow_mcp.infrastructure.entra.obo import ConfigObo, JetonsEntra
from agentinsurflow_mcp.infrastructure.gateway.client import ClientGateway

CONTRAT = "AIF/2026/0042"
QUESTION = "Jean Dupont conduit-il avec un malus ?"
OID = "oid-gestionnaire-secret"
TRACE_ID = "0af7651916cd43dd8448eb211c80319c"
TRACEPARENT = f"00-{TRACE_ID}-b7ad6b7169203331-01"


class Gateway:
    """Gateway simulée : enregistre les requêtes sortantes du serveur MCP."""

    def __init__(self) -> None:
        self.requetes: list[httpx.Request] = []

    def __call__(self, requete: httpx.Request) -> httpx.Response:
        self.requetes.append(requete)
        if requete.url.path == "/api/extraits":
            return httpx.Response(200, json={"statut": "OK", "resultats": []})
        if requete.method == "GET":
            return httpx.Response(200, json={"numero_contrat": CONTRAT})
        return httpx.Response(204)


def _app(gateway: Gateway, *, jetons: Any = None) -> Any:
    client = ClientGateway(
        httpx.AsyncClient(transport=httpx.MockTransport(gateway)), "http://gateway"
    )
    serveur = ServeurMcp(jetons or JetonsEntra(_cfg_obo()), client, client, "test")
    application = creer_app(serveur)
    application.state.config_auth = config_auth()
    application.state.jwks = FauxJwks()
    return application


def _cfg_obo() -> ConfigObo:
    return ConfigObo(  # type: ignore[call-arg]
        azure_tenant_id="t",
        mcp_api_client_id="m",
        rag_api_client_id="r",
        underwriting_api_client_id="u",
    )


@pytest.fixture(autouse=True)
def _obo_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(obo, "_jeton_obo", lambda cfg, jeton, client: f"obo-{client}")


def _par_nom(spans: InMemorySpanExporter, nom: str) -> list[ReadableSpan]:
    return [s for s in spans.get_finished_spans() if s.name == nom]


def _un(spans: InMemorySpanExporter, nom: str) -> dict[str, Any]:
    trouves = _par_nom(spans, nom)
    assert len(trouves) == 1, [s.name for s in spans.get_finished_spans()]
    return dict(trouves[0].attributes or {})


async def test_lister_les_outils_est_trace(spans: InMemorySpanExporter) -> None:
    async with session_mcp(_app(Gateway()), creer(AZP_ORCHESTRATEUR)) as s:
        await s.list_tools()
    attributs = _un(spans, "mcp.lister_outils")
    assert attributs["appelant.azp"] == AZP_ORCHESTRATEUR
    assert attributs["outils.nombre"] == 3  # evaluer_risque n'existe pas encore


async def test_search_rag_trace_la_question_par_son_empreinte(spans: InMemorySpanExporter) -> None:
    async with session_mcp(_app(Gateway()), creer(AZP_REDACTEUR)) as s:
        await s.call_tool("search_rag", {"question": QUESTION})
    attributs = _un(spans, "mcp.outil")
    assert attributs["mcp.outil"] == "search_rag"
    assert attributs["appelant.azp"] == AZP_REDACTEUR
    assert attributs["autorisation.decision"] == "allow"
    assert attributs["autorisation.regle"] == "matrice:redacteur"
    assert attributs["resultat.code"] == "OK"
    assert attributs["isError"] is False
    assert attributs["question.sha256"] == hashlib.sha256(QUESTION.encode()).hexdigest()
    assert attributs["question.longueur"] == len(QUESTION)
    assert _un(spans, "obo.echanger") == {"obo.cible": "rag", "obo.reussi": True}
    assert _un(spans, "gateway.appel") == {"http.route": "/api/extraits", "http.status_code": 200}


async def test_get_contrat_trace_le_gabarit_de_la_route(spans: InMemorySpanExporter) -> None:
    async with session_mcp(_app(Gateway()), creer(AZP_ORCHESTRATEUR)) as s:
        await s.call_tool("get_contrat", {"numero_contrat": CONTRAT})
    assert _un(spans, "mcp.outil")["contrat.present"] is True
    assert _un(spans, "obo.echanger")["obo.cible"] == "underwriting"
    assert _un(spans, "gateway.appel") == {
        "http.route": "/api/contrats/{numero_contrat}",
        "http.status_code": 200,
    }


async def test_ecritures_tracent_le_statut_cible(spans: InMemorySpanExporter) -> None:
    args = {"numero_contrat": CONTRAT, "statut": "REVUE_HUMAINE"}
    async with session_mcp(_app(Gateway()), creer(AZP_ORCHESTRATEUR)) as s:
        await s.call_tool("update_statut_dossier", args)
    attributs = _un(spans, "mcp.outil")
    assert (attributs["statut.cible"], attributs["contrat.present"]) == ("REVUE_HUMAINE", True)
    assert _un(spans, "gateway.appel")["http.route"] == "/api/contrats/{numero_contrat}/statut"


async def test_refus_trace_la_decision_deny_sans_appel_sortant(
    spans: InMemorySpanExporter,
) -> None:
    gateway = Gateway()
    args = {"numero_contrat": CONTRAT, "statut": "ACCEPTE"}
    async with session_mcp(_app(gateway), creer(AZP_REDACTEUR)) as s:
        r = await s.call_tool("update_statut_dossier", args)
    attributs = _un(spans, "mcp.outil")
    assert (attributs["autorisation.decision"], attributs["autorisation.regle"]) == (
        "deny",
        "matrice:redacteur",
    )
    assert (attributs["resultat.code"], attributs["isError"]) == ("UNAUTHORIZED_TOOL", True)
    assert r.isError and not gateway.requetes
    assert not _par_nom(spans, "obo.echanger")


async def test_azp_inconnu_est_refuse_par_matrice_inconnu(spans: InMemorySpanExporter) -> None:
    async with session_mcp(_app(Gateway()), creer("azp-inconnu")) as s:
        await s.call_tool("search_rag", {"question": "q"})
    assert _un(spans, "mcp.outil")["autorisation.regle"] == "matrice:inconnu"


async def test_obo_refuse_est_trace(spans: InMemorySpanExporter) -> None:
    application = _app(Gateway(), jetons=JetonsEntra(None))
    async with session_mcp(application, creer(AZP_REDACTEUR)) as s:
        await s.call_tool("search_rag", {"question": "q"})
    assert _un(spans, "obo.echanger") == {"obo.cible": "rag", "obo.reussi": False}
    assert _un(spans, "mcp.outil")["resultat.code"] == "DOSSIERS_INDISPONIBLES"


async def test_traceparent_entrant_relie_mcp_outil_et_la_requete_vers_la_gateway(
    spans: InMemorySpanExporter,
) -> None:
    gateway = Gateway()
    async with session_mcp(
        _app(gateway), creer(AZP_ORCHESTRATEUR), {"traceparent": TRACEPARENT}
    ) as s:
        await s.call_tool("get_contrat", {"numero_contrat": CONTRAT})
    assert format(_par_nom(spans, "mcp.outil")[0].context.trace_id, "032x") == TRACE_ID
    sortant = gateway.requetes[0].headers["traceparent"]
    assert sortant.split("-")[1] == TRACE_ID
    # le parent de la requête sortante est le span gateway.appel (pas l'entrant)
    appel = _par_nom(spans, "gateway.appel")[0]
    assert sortant.split("-")[2] == format(appel.context.span_id, "016x")


def _textes(spans: InMemorySpanExporter) -> list[str]:
    """Tout ce qu'un span exporte : attributs, événements et description du statut."""
    return [
        str(v)
        for sp in spans.get_finished_spans()
        for attributs in [sp.attributes, *(e.attributes for e in sp.events)]
        for v in (attributs or {}).values()
    ] + [sp.status.description or "" for sp in spans.get_finished_spans()]


async def test_arguments_invalides_ne_fuient_pas_dans_les_spans(
    spans: InMemorySpanExporter,
) -> None:
    # top_k invalide : la validation pydantic de FastMCP cite input_value=<la valeur saisie>
    args = {"question": QUESTION, "top_k": f"{CONTRAT} {QUESTION}"}
    async with session_mcp(_app(Gateway()), creer(AZP_REDACTEUR)) as s:
        r = await s.call_tool("search_rag", args)
        assert r.isError
        inconnu = {"numero_contrat": CONTRAT, "statut": f"{CONTRAT} {QUESTION}"}
    async with session_mcp(_app(Gateway()), creer(AZP_ORCHESTRATEUR)) as s:
        await s.call_tool("update_statut_dossier", {**inconnu, "validation": 3})
    for interdit in (CONTRAT, "0042", "Dupont", QUESTION):
        assert not any(interdit in t for t in _textes(spans)), interdit
    erreur = _par_nom(spans, "mcp.outil")[0]
    assert (erreur.attributes or {})["resultat.code"] == "ERREUR"
    assert erreur.status.status_code.name == "ERROR"
    assert any(
        (sp.attributes or {}).get("statut.cible") == "INCONNU" for sp in spans.get_finished_spans()
    )


async def test_aucune_donnee_personnelle_dans_les_spans(spans: InMemorySpanExporter) -> None:
    jeton = creer(AZP_ORCHESTRATEUR, oid=OID)
    async with session_mcp(_app(Gateway()), jeton) as s:
        await s.list_tools()
        await s.call_tool("search_rag", {"question": QUESTION})
        await s.call_tool("get_contrat", {"numero_contrat": CONTRAT})
        await s.call_tool("update_statut_dossier", {"numero_contrat": CONTRAT, "statut": "X"})
    textes = _textes(spans)
    assert textes
    for interdit in (CONTRAT, "0042", "Dupont", QUESTION, jeton, OID, "obo-"):
        assert not any(interdit in t for t in textes), interdit


async def test_sante_n_est_pas_tracee(spans: InMemorySpanExporter) -> None:
    application = _app(Gateway())
    async with application.router.lifespan_context(application):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application), base_url="http://test"
        ) as http:
            assert (await http.get("/health")).status_code == 200
    assert not spans.get_finished_spans()
