"""Unitaires — adaptateur HTTP de la gateway (``httpx.MockTransport``, sans socket)."""

from __future__ import annotations

import json

import httpx
import pytest

from agentinsurflow_mcp.domain.models import ErreurOutil
from agentinsurflow_mcp.infrastructure.gateway.client import ClientGateway


def client(
    reponse: httpx.Response | Exception, vues: list[httpx.Request] | None = None
) -> ClientGateway:
    def gerer(requete: httpx.Request) -> httpx.Response:
        if vues is not None:
            vues.append(requete)
        if isinstance(reponse, Exception):
            raise reponse
        return reponse

    http = httpx.AsyncClient(transport=httpx.MockTransport(gerer))
    return ClientGateway(http, "http://gw/")


async def test_lire_contrat_url_encodee_et_bearer() -> None:
    vues: list[httpx.Request] = []
    gw = client(httpx.Response(200, json={"numero_contrat": "AIF/1"}), vues)
    assert await gw.lire_contrat("obo-u", "AIF/1") == {"numero_contrat": "AIF/1"}
    assert vues[0].url.raw_path == b"/api/contrats/AIF%2F1"
    assert vues[0].headers["authorization"] == "Bearer obo-u"


async def test_chercher_envoie_question_et_top_k() -> None:
    vues: list[httpx.Request] = []
    gw = client(httpx.Response(200, json={"statut": "OK", "resultats": []}), vues)
    await gw.chercher("obo-r", "franchise ?", 3)
    assert vues[0].url.path == "/api/extraits"
    assert dict(vues[0].url.params) == {"question": "franchise ?", "top_k": "3"}


async def test_chercher_sans_top_k_ne_l_envoie_pas() -> None:
    vues: list[httpx.Request] = []
    await client(httpx.Response(200, json={"statut": "OK"}), vues).chercher("j", "q", None)
    assert "top_k" not in vues[0].url.params


async def test_chercher_statut_not_found_in_corpus() -> None:
    gw = client(httpx.Response(200, json={"statut": "NOT_FOUND_IN_CORPUS", "resultats": []}))
    with pytest.raises(ErreurOutil) as exc:
        await gw.chercher("j", "q", None)
    assert exc.value.code == "NOT_FOUND_IN_CORPUS"


async def test_ecritures_put_brouillon_et_statut() -> None:
    vues: list[httpx.Request] = []
    gw = client(httpx.Response(204), vues)
    await gw.enregistrer_brouillon("j", "AIF/1", {"a": 1})
    await gw.changer_statut("j", "AIF/1", {"statut": "x"})
    assert [(v.method, v.url.raw_path) for v in vues] == [
        ("PUT", b"/api/contrats/AIF%2F1/brouillon"),
        ("PUT", b"/api/contrats/AIF%2F1/statut"),
    ]
    assert json.loads(vues[0].content) == {"a": 1}


@pytest.mark.parametrize(
    ("statut", "code"),
    [
        (404, "CONTRAT_INTROUVABLE"),
        (400, "ARGUMENTS_INVALIDES"),
        (422, "ARGUMENTS_INVALIDES"),
        (503, "DOSSIERS_INDISPONIBLES"),
        (500, "DOSSIERS_INDISPONIBLES"),
    ],
)
async def test_statuts_http_vers_codes(statut: int, code: str) -> None:
    with pytest.raises(ErreurOutil) as exc:
        await client(httpx.Response(statut)).lire_contrat("j", "X")
    assert exc.value.code == code


async def test_transport_en_echec_dossiers_indisponibles() -> None:
    with pytest.raises(ErreurOutil) as exc:
        await client(httpx.ConnectError("boom")).lire_contrat("j", "X")
    assert exc.value.code == "DOSSIERS_INDISPONIBLES"


async def test_corps_non_json_dossiers_indisponibles() -> None:
    with pytest.raises(ErreurOutil) as exc:
        await client(httpx.Response(200, content=b"<html>")).lire_contrat("j", "X")
    assert exc.value.code == "DOSSIERS_INDISPONIBLES"


async def test_404_du_corpus_est_une_panne_pas_un_corpus_muet() -> None:
    with pytest.raises(ErreurOutil) as exc:
        await client(httpx.Response(404)).chercher("j", "q", None)
    assert exc.value.code == "DOSSIERS_INDISPONIBLES"


async def test_400_relaie_le_code_du_problemdetails_sans_title_ni_detail() -> None:
    corps = {"code": "DECISION_ABSENTE", "title": "Écriture refusée", "detail": "secret-perso"}
    with pytest.raises(ErreurOutil) as exc:
        await client(httpx.Response(400, json=corps)).changer_statut("j", "X", {})
    assert exc.value.code == "ARGUMENTS_INVALIDES"
    assert "DECISION_ABSENTE" in str(exc.value)
    assert "secret-perso" not in str(exc.value)
    assert "Écriture refusée" not in str(exc.value)
