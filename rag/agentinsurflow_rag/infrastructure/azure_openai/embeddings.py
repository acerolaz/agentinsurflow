"""Adaptateur Azure OpenAI du port ``ClientEmbeddings`` (``text-embedding-3-small``, 1 536 dim.)."""

from __future__ import annotations

from azure.core.exceptions import ClientAuthenticationError
from openai import OpenAI, OpenAIError

from ...domain.ports import ClientEmbeddings, ErreurEmbeddings
from .config import ConfigLLM
from .llm import client_openai


def fabrique_embeddings(cfg: ConfigLLM) -> ClientEmbeddings | None:
    """Le ClientEmbeddings, ou None s'il n'est pas configuré (ingestion et recherche en 503)."""
    if not (cfg.azure_openai_endpoint and cfg.azure_openai_embedding_deployment):
        return None
    return AzureEmbeddings(client_openai(cfg), cfg.azure_openai_embedding_deployment)


class AzureEmbeddings:
    """Un appel par lot de textes ; l'ordre des vecteurs suit celui des textes."""

    def __init__(self, client: OpenAI, deploiement: str) -> None:
        self._client, self.modele = client, deploiement

    def vectoriser(self, textes: list[str]) -> list[list[float]]:
        try:
            reponse = self._client.embeddings.create(model=self.modele, input=textes)
        except (OpenAIError, ClientAuthenticationError) as exc:
            raise ErreurEmbeddings(f"erreur du fournisseur d'embeddings : {exc!r}") from exc
        return [d.embedding for d in sorted(reponse.data, key=lambda d: d.index)]
