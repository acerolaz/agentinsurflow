"""Unitaires — configuration et adaptateur Azure OpenAI, sans réseau (httpx.MockTransport)."""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest
from openai import AzureOpenAI

from agentinsurflow.llm import AzureLLM, ConfigLLM, ErreurLLM, fabrique_llm

ENDPOINT = "https://exemple.openai.azure.com"


def _config(**valeurs: str) -> ConfigLLM:
    defaut = {
        "azure_openai_endpoint": ENDPOINT,
        "azure_openai_api_key": "cle-de-test",
        "azure_openai_deployment": "chat"
    }
    return ConfigLLM(_env_file=None, **{**defaut, **valeurs})  # type: ignore[arg-type]


def _azure(repondre: Callable[[httpx.Request], httpx.Response]) -> AzureLLM:
    client = AzureOpenAI(
        azure_endpoint=ENDPOINT,
        api_key="cle-de-test",
        api_version="2024-10-21",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(repondre)),
    )
    return AzureLLM(client, "chat")


def test_sans_cle_pas_de_llm() -> None:
    assert fabrique_llm(_config(azure_openai_api_key="")) is None


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
    assert requete.url.path == "/openai/deployments/chat/chat/completions"
    assert requete.url.params["api-version"] == "2024-10-21"
    assert requete.headers["api-key"] == "cle-de-test"
    assert [m["role"] for m in json.loads(requete.content)["messages"]] == ["system", "user"]


def test_erreur_du_fournisseur_leve_erreur_llm() -> None:
    llm = _azure(lambda requete: httpx.Response(500, json={"error": {"message": "panne"}}))
    with pytest.raises(ErreurLLM):
        llm.completer("sys", "Question")
