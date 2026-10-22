"""Unitaires — adaptateur HTTP de la Function de calcul (``httpx.MockTransport``, sans socket)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from agentinsurflow_mcp.domain.models import ErreurOutil
from agentinsurflow_mcp.infrastructure.fonction_calcul import client as module
from agentinsurflow_mcp.infrastructure.fonction_calcul.client import ClientCalcul, ConfigCalcul

FAITS = {"crm": "0.9", "suspensions": 0}
RESULTAT = {"decision": "ACCEPTE", "version_bareme": "bareme-2026.10-v1", "prime": "819.73"}


class _Jeton:
    token = "jeton-fonction"


class _Credential:
    def get_token(self, portee: str) -> _Jeton:
        return _Jeton()


@pytest.fixture(autouse=True)
def _credential_factice(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "credential_application", lambda *a, **k: _Credential())


def client(
    reponse: httpx.Response | Exception,
    vues: list[httpx.Request] | None = None,
    **cfg: Any,
) -> ClientCalcul:
    def gerer(requete: httpx.Request) -> httpx.Response:
        if vues is not None:
            vues.append(requete)
        if isinstance(reponse, Exception):
            raise reponse
        return reponse

    http = httpx.AsyncClient(transport=httpx.MockTransport(gerer))
    return ClientCalcul(
        http,
        ConfigCalcul(calcul_url="http://calcul/", **{"calcul_audience": "api://calcul", **cfg}),
    )


@pytest.mark.parametrize("route", ["evaluer", "calculer"])
async def test_200_renvoie_le_json_et_poste_les_faits(route: str) -> None:
    vues: list[httpx.Request] = []
    calc = client(httpx.Response(200, json=RESULTAT), vues)
    assert await getattr(calc, route)(FAITS) == RESULTAT
    assert (vues[0].method, str(vues[0].url)) == ("POST", f"http://calcul/{route}")
    assert json.loads(vues[0].content) == FAITS


async def test_422_hors_bareme_nomme_le_champ() -> None:
    corps = {"code": "DONNEE_HORS_BAREME", "champ": "type_usage"}
    with pytest.raises(ErreurOutil) as exc:
        await client(httpx.Response(422, json=corps)).evaluer(FAITS)
    assert exc.value.code == "DONNEE_HORS_BAREME"
    assert "type_usage" in str(exc.value)


@pytest.mark.parametrize(
    "reponse",
    [
        httpx.Response(400, json={"code": "REQUETE_INVALIDE"}),
        httpx.Response(401),
        httpx.Response(500),
        httpx.Response(200, content=b"<html>"),
        httpx.ConnectError("boom"),
        httpx.ReadTimeout("lent"),
    ],
)
async def test_autres_echecs_calcul_indisponible(reponse: httpx.Response | Exception) -> None:
    with pytest.raises(ErreurOutil) as exc:
        await client(reponse).calculer(FAITS)
    assert exc.value.code == "CALCUL_INDISPONIBLE"


async def test_400_est_journalise_sans_corps(caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(ErreurOutil):
        await client(httpx.Response(400, json={"code": "REQUETE_INVALIDE"})).evaluer(FAITS)
    assert "requête de calcul invalide" in caplog.text
    assert "0.9" not in caplog.text


async def test_sans_audience_calcul_indisponible_sans_appel_http() -> None:
    vues: list[httpx.Request] = []
    with pytest.raises(ErreurOutil) as exc:
        await client(httpx.Response(200, json=RESULTAT), vues, calcul_audience=None).evaluer(FAITS)
    assert exc.value.code == "CALCUL_INDISPONIBLE"
    assert vues == []


async def test_avec_audience_bearer_du_fournisseur(monkeypatch: pytest.MonkeyPatch) -> None:
    portees: list[str] = []

    class Credential:
        def get_token(self, portee: str) -> _Jeton:
            portees.append(portee)
            return _Jeton()

    monkeypatch.setattr(module, "credential_application", lambda *a, **k: Credential())
    vues: list[httpx.Request] = []
    await client(httpx.Response(200, json=RESULTAT), vues).evaluer(FAITS)
    assert vues[0].headers["authorization"] == "Bearer jeton-fonction"
    assert portees == ["api://calcul/.default"]


async def test_sans_configuration_entra_calcul_indisponible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.undo()  # vraie fabrique : aucune identité configurée
    vues: list[httpx.Request] = []
    with pytest.raises(ErreurOutil) as exc:
        await client(httpx.Response(200, json=RESULTAT), vues).evaluer(FAITS)
    assert exc.value.code == "CALCUL_INDISPONIBLE"
    assert vues == []


async def test_delai_de_10_secondes() -> None:
    vues: list[httpx.Request] = []
    await client(httpx.Response(200, json=RESULTAT), vues).evaluer(FAITS)
    assert vues[0].extensions["timeout"]["read"] == 10.0
