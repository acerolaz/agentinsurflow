"""Unitaires — configuration et adaptateur Azure OpenAI, sans réseau (httpx.MockTransport)."""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest
from azure.core.exceptions import ClientAuthenticationError
from openai import OpenAI

from agentinsurflow.llm import AzureLLM, ConfigLLM, ErreurLLM, fabrique_llm

ENDPOINT = "https://exemple.openai.azure.com"


def _config(**valeurs: str) -> ConfigLLM:
    defaut = {
        "azure_openai_endpoint": ENDPOINT,
        "azure_openai_api_key": "cle-de-test",
        "azure_openai_deployment": "chat",
    }
    return ConfigLLM(_env_file=None, **{**defaut, **valeurs})  # type: ignore[arg-type]


def _azure(
    repondre: Callable[[httpx.Request], httpx.Response],
    cle: str | Callable[[], str] = "cle-de-test",
) -> AzureLLM:
    client = OpenAI(
        base_url=f"{ENDPOINT}/openai/v1/",
        api_key=cle,
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(repondre)),
    )
    return AzureLLM(client, "chat")


def test_sans_endpoint_ni_deploiement_pas_de_llm() -> None:
    assert fabrique_llm(_config(azure_openai_endpoint="")) is None
    assert fabrique_llm(_config(azure_openai_deployment="")) is None


def test_sans_cle_l_adaptateur_passe_par_entra_id() -> None:
    llm = fabrique_llm(_config(azure_openai_api_key=""))  # aucun appel réseau à la création
    assert isinstance(llm, AzureLLM) and llm.modele == "chat"


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
    assert requete.url.path == "/openai/v1/chat/completions"
    assert requete.headers["authorization"] == "Bearer cle-de-test"
    corps = json.loads(requete.content)
    assert corps["model"] == "chat"  # le nom du déploiement Azure
    assert [m["role"] for m in corps["messages"]] == ["system", "user"]


def test_jeton_entra_envoye_en_bearer() -> None:
    recu: list[httpx.Request] = []

    def repondre(requete: httpx.Request) -> httpx.Response:
        recu.append(requete)
        return httpx.Response(401, json={"error": {"message": "rôle manquant"}})

    with pytest.raises(ErreurLLM):
        _azure(repondre, cle=lambda: "jeton-entra").completer("sys", "Question")
    assert recu[0].headers["authorization"] == "Bearer jeton-entra"


def test_echec_d_authentification_entra_leve_erreur_llm() -> None:
    def sans_identite() -> str:
        raise ClientAuthenticationError("aucune identité disponible")

    with pytest.raises(ErreurLLM):
        _azure(lambda requete: httpx.Response(200), cle=sans_identite).completer("sys", "Q")


def test_erreur_du_fournisseur_leve_erreur_llm() -> None:
    llm = _azure(lambda requete: httpx.Response(500, json={"error": {"message": "panne"}}))
    with pytest.raises(ErreurLLM):
        llm.completer("sys", "Question")


@pytest.mark.parametrize(
    "endpoint",
    [ENDPOINT, f"{ENDPOINT}/", f"{ENDPOINT}/openai/v1", f"{ENDPOINT}/openai/v1/"],
)
def test_endpoint_accepte_avec_ou_sans_suffixe_v1(endpoint: str) -> None:
    llm = fabrique_llm(_config(azure_openai_endpoint=endpoint))
    assert isinstance(llm, AzureLLM)
    assert str(llm._client.base_url) == f"{ENDPOINT}/openai/v1/"
