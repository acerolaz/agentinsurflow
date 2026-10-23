"""Unitaires — configuration et adaptateur Azure OpenAI, sans réseau (httpx.MockTransport)."""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest
from azure.core.exceptions import ClientAuthenticationError
from openai import OpenAI

from agentinsurflow_rag.domain.ports import ErreurLLM
from agentinsurflow_rag.infrastructure.azure_openai.config import ConfigLLM
from agentinsurflow_rag.infrastructure.azure_openai.llm import (
    AzureLLM,
    client_openai,
    fabrique_llm,
)
from agentinsurflow_rag.infrastructure.entra import application as module_llm

ENDPOINT = "http://gateway:8000/api/llm"


def _config(**valeurs: str) -> ConfigLLM:
    defaut = {
        "azure_openai_endpoint": ENDPOINT,
        "azure_openai_deployment": "chat",
        "llm_audience": "api://llm-test",
        "azure_tenant_id": "tenant-test",
        "rag_api_client_id": "rag-test",
        "rag_client_secret": "secret-local",
    }
    return ConfigLLM(_env_file=None, **{**defaut, **valeurs})  # type: ignore[arg-type]


def _azure(
    repondre: Callable[[httpx.Request], httpx.Response],
    cle: str | Callable[[], str] = "cle-de-test",
) -> AzureLLM:
    client = OpenAI(
        base_url=f"{ENDPOINT}/v1/",
        api_key=cle,
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(repondre)),
    )
    return AzureLLM(client, "chat")


def test_sans_endpoint_ni_deploiement_pas_de_llm() -> None:
    assert fabrique_llm(_config(azure_openai_endpoint="")) is None
    assert fabrique_llm(_config(azure_openai_deployment="")) is None


def test_configure_donne_l_adaptateur_azure() -> None:
    llm = fabrique_llm(_config())
    assert isinstance(llm, AzureLLM) and llm.modele == "chat"


def test_appelle_le_deploiement_et_rend_le_texte() -> None:
    recu: list[httpx.Request] = []

    def repondre(requete: httpx.Request) -> httpx.Response:
        recu.append(requete)
        return httpx.Response(
            200,
            json={
                "id": "c1",
                "object": "chat.completion",
                "created": 0,
                "model": "chat",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Bonjour."},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    assert _azure(repondre).completer("sys", "Question") == "Bonjour."
    requete = recu[0]
    assert requete.url.path == "/api/llm/v1/chat/completions"
    assert requete.headers["authorization"] == "Bearer cle-de-test"
    corps = json.loads(requete.content)
    assert corps["model"] == "chat"  # le nom du déploiement Azure
    assert [m["role"] for m in corps["messages"]] == ["system", "user"]


def test_jeton_application_envoye_en_bearer() -> None:
    recu: list[httpx.Request] = []

    def repondre(requete: httpx.Request) -> httpx.Response:
        recu.append(requete)
        return httpx.Response(401, json={"error": {"message": "rôle manquant"}})

    with pytest.raises(ErreurLLM):
        _azure(repondre, cle=lambda: "jeton-entra").completer("sys", "Question")
    assert recu[0].headers["authorization"] == "Bearer jeton-entra"


def test_echec_d_authentification_application_leve_erreur_llm() -> None:
    def sans_identite() -> str:
        raise ClientAuthenticationError("aucune identité disponible")

    with pytest.raises(ErreurLLM):
        _azure(lambda requete: httpx.Response(200), cle=sans_identite).completer("sys", "Q")


def test_erreur_du_fournisseur_leve_erreur_llm() -> None:
    llm = _azure(lambda requete: httpx.Response(500, json={"error": {"message": "panne"}}))
    with pytest.raises(ErreurLLM):
        llm.completer("sys", "Question")


class _Credential:
    """Double d'une credential azure-identity : mémorise sa construction et la portée demandée."""

    instances: list[_Credential] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.args, self.kwargs, self.portees = args, kwargs, []
        _Credential.instances.append(self)

    def get_token(self, *portees: str, **_: object) -> object:
        self.portees.extend(portees)
        if len(self.args) > 2 and callable(self.args[2]):
            self.args[2]()  # l'assertion fédérée : jeton de l'identité managée
        return type("Jeton", (), {"token": "jeton-app", "expires_on": 4_102_444_800})()


@pytest.fixture
def credentials(monkeypatch: pytest.MonkeyPatch) -> list[_Credential]:
    _Credential.instances = []
    for nom in ("ClientSecretCredential", "ClientAssertionCredential", "ManagedIdentityCredential"):
        monkeypatch.setattr(module_llm, nom, type(nom, (_Credential,), {}))
    return _Credential.instances


@pytest.mark.parametrize("endpoint", [ENDPOINT, f"{ENDPOINT}/"])
def test_base_url_est_la_gateway_avec_v1(endpoint: str) -> None:
    client = client_openai(_config(azure_openai_endpoint=endpoint))
    assert str(client.base_url) == f"{ENDPOINT}/v1/"


def _jeton(client: OpenAI) -> str:
    assert client._api_key_provider is not None  # fournisseur de jeton, pas une clé figée
    return client._api_key_provider()


def test_secret_local_d_abord_portee_de_l_audience_llm(credentials: list[_Credential]) -> None:
    client = client_openai(_config(azure_uami_client_id="uami-test"))
    assert _jeton(client) == "jeton-app"
    (cred,) = credentials
    assert type(cred).__name__ == "ClientSecretCredential"
    assert cred.args == ("tenant-test", "rag-test", "secret-local")
    assert cred.portees == ["api://llm-test/.default"]


def test_sans_secret_identite_managee_federee(credentials: list[_Credential]) -> None:
    client = client_openai(_config(rag_client_secret="", azure_uami_client_id="uami-test"))
    assert _jeton(client) == "jeton-app"
    assertion = next(c for c in credentials if type(c).__name__ == "ClientAssertionCredential")
    assert assertion.args[:2] == ("tenant-test", "rag-test")
    identite = next(c for c in credentials if type(c).__name__ == "ManagedIdentityCredential")
    assert identite.kwargs == {"client_id": "uami-test"}
    assert identite.portees == ["api://AzureADTokenExchange/.default"]
    assert assertion.portees == ["api://llm-test/.default"]


def test_aucune_cle_dans_la_configuration() -> None:
    assert not any("api_key" in nom for nom in ConfigLLM.model_fields)


def test_sans_audience_erreur_explicite() -> None:
    with pytest.raises(ErreurLLM, match="LLM_AUDIENCE"):
        client_openai(_config(llm_audience=""))


def test_sans_identite_erreur_explicite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(
        "AZURE_UAMI_CLIENT_ID", raising=False
    )  # hermétique : `.env` exporté par make
    with pytest.raises(ErreurLLM, match="RAG_CLIENT_SECRET"):
        client_openai(_config(rag_client_secret=""))


def test_erreur_llm_est_un_503_problemdetails_sans_detail() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from agentinsurflow_rag.api.erreurs import installer_gestionnaires

    app = FastAPI()
    installer_gestionnaires(app)

    @app.get("/t")
    def _() -> None:
        raise ErreurLLM("LLM_AUDIENCE absente (détail interne)")

    r = TestClient(app).get("/t")
    assert r.status_code == 503 and r.json()["code"] == "LLM_INDISPONIBLE"
    assert "LLM_AUDIENCE" not in r.text
