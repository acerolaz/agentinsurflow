"""Unitaires — port d'embeddings : FakeEmbeddings (déterministe), adaptateur Azure (HTTP simulé)."""

from __future__ import annotations

import math
from collections.abc import Callable

import httpx
import pytest
from openai import OpenAI

from agentinsurflow_rag.domain.ports import ErreurEmbeddings
from agentinsurflow_rag.infrastructure.azure_openai.config import ConfigLLM
from agentinsurflow_rag.infrastructure.azure_openai.embeddings import (
    AzureEmbeddings,
    fabrique_embeddings,
)
from fakes import FakeEmbeddings

ENDPOINT = "http://gateway:8000/api/llm"


def cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True)) / (
        math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    )


def test_fake_embeddings_textes_proches_plus_similaires() -> None:
    a, b, c = FakeEmbeddings().vectoriser(
        ["bonus malus coefficient", "coefficient bonus malus", "recette de cuisine"]
    )
    assert cos(a, b) > 0.99 and cos(a, c) < 0.2


def test_fake_embeddings_jamais_nul_et_norme() -> None:
    (vecteur,) = FakeEmbeddings().vectoriser(["???"])
    assert any(vecteur)
    assert math.isclose(math.sqrt(sum(x * x for x in vecteur)), 1.0)
    assert len(vecteur) == 1536


def test_fake_embeddings_trace_les_appels() -> None:
    emb = FakeEmbeddings()
    emb.vectoriser(["a", "b"])
    assert emb.appels == [["a", "b"]]


def _azure(repondre: Callable[[httpx.Request], httpx.Response]) -> AzureEmbeddings:
    client = OpenAI(
        base_url=f"{ENDPOINT}/v1/",
        api_key="cle-de-test",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(repondre)),
    )
    return AzureEmbeddings(client, "text-embedding-3-small")


def test_azure_embeddings_rend_les_vecteurs_dans_l_ordre() -> None:
    recu: list[httpx.Request] = []

    def repondre(requete: httpx.Request) -> httpx.Response:
        recu.append(requete)
        donnees = [{"object": "embedding", "index": i, "embedding": [float(i)] * 3} for i in (1, 0)]
        return httpx.Response(200, json={"object": "list", "data": donnees, "model": "m"})

    assert _azure(repondre).vectoriser(["a", "b"]) == [[0.0] * 3, [1.0] * 3]
    assert recu[0].url.path == "/api/llm/v1/embeddings"


def test_azure_embeddings_erreur_fournisseur_devient_erreur_embeddings() -> None:
    emb = _azure(lambda requete: httpx.Response(500, json={"error": {"message": "panne"}}))
    with pytest.raises(ErreurEmbeddings):
        emb.vectoriser(["a"])


def _config(**valeurs: str) -> ConfigLLM:
    defaut = {
        "azure_openai_endpoint": ENDPOINT,
        "llm_audience": "api://llm-test",
        "azure_tenant_id": "tenant-test",
        "rag_api_client_id": "rag-test",
        "rag_client_secret": "secret-local",
        "azure_openai_embedding_deployment": "text-embedding-3-small",
    }
    return ConfigLLM(_env_file=None, **{**defaut, **valeurs})  # type: ignore[arg-type]


def test_fabrique_embeddings_none_sans_deploiement() -> None:
    assert fabrique_embeddings(_config(azure_openai_embedding_deployment="")) is None
    assert fabrique_embeddings(_config(azure_openai_endpoint="")) is None


def test_fabrique_embeddings_donne_l_adaptateur_azure() -> None:
    emb = fabrique_embeddings(_config())
    assert isinstance(emb, AzureEmbeddings) and emb.modele == "text-embedding-3-small"
