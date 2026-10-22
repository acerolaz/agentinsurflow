"""Adaptateur Azure OpenAI du port ``ClientLLM`` (repris de Kaldera, ``llm.py``).

Le SDK ``openai`` n'apparaît qu'ici. Aucune clé : rag appelle la gateway (``/api/llm``) avec un
jeton d'application pour l'audience ``LLM_AUDIENCE`` (rôle ``LLM``) ; la gateway échange son propre
jeton avec Foundry. Même ordre que l'OBO : ``RAG_CLIENT_SECRET`` en local, sinon identité managée
fédérée.
"""

from __future__ import annotations

from collections.abc import Callable

from azure.core.exceptions import ClientAuthenticationError
from azure.identity import (
    ClientAssertionCredential,
    ClientSecretCredential,
    ManagedIdentityCredential,
    get_bearer_token_provider,
)
from openai import OpenAI, OpenAIError

from ...domain.corpus import hash_contenu
from ...domain.ports import ClientLLM, ErreurLLM
from ..entra.obo import PORTEE_FEDERATION
from ..otel.telemetrie import tracer
from .config import ConfigLLM


def _fournisseur_jeton(cfg: ConfigLLM) -> Callable[[], str]:
    """Jeton d'application de rag pour l'audience du LLM (rafraîchi par le SDK azure-identity)."""
    if not cfg.llm_audience:
        raise ErreurLLM("LLM_AUDIENCE absente : audience du jeton d'application pour le LLM")
    secret = cfg.rag_client_secret.get_secret_value()
    credential: ClientSecretCredential | ClientAssertionCredential
    if secret:
        credential = ClientSecretCredential(cfg.azure_tenant_id, cfg.rag_api_client_id, secret)
    elif cfg.azure_uami_client_id:
        identite = ManagedIdentityCredential(client_id=cfg.azure_uami_client_id)
        credential = ClientAssertionCredential(
            cfg.azure_tenant_id,
            cfg.rag_api_client_id,
            lambda: identite.get_token(PORTEE_FEDERATION).token,
        )
    else:
        raise ErreurLLM("ni RAG_CLIENT_SECRET (local) ni AZURE_UAMI_CLIENT_ID (Azure)")
    return get_bearer_token_provider(credential, f"{cfg.llm_audience}/.default")


def client_openai(cfg: ConfigLLM) -> OpenAI:
    """Client de l'API v1 par la gateway (``…/api/llm``), partagé par LLM et embeddings."""
    return OpenAI(
        base_url=f"{cfg.azure_openai_endpoint.rstrip('/')}/v1/",
        api_key=_fournisseur_jeton(cfg),
        timeout=cfg.llm_delai_s,
        max_retries=0,
    )


def fabrique_llm(cfg: ConfigLLM) -> ClientLLM | None:
    """Le ClientLLM, ou None s'il n'est pas configuré (⇒ mode dégradé)."""
    if not (cfg.azure_openai_endpoint and cfg.azure_openai_deployment):
        return None
    return AzureLLM(client_openai(cfg), cfg.azure_openai_deployment)


class AzureLLM:
    """Azure OpenAI (SDK ``openai``, API v1) derrière le port ClientLLM."""

    def __init__(self, client: OpenAI, deploiement: str) -> None:
        self._client, self.modele = client, deploiement

    def completer(self, systeme: str, question: str) -> str:
        with tracer.start_as_current_span("llm.completer") as span:
            span.set_attributes(
                {"gen_ai.request.model": self.modele, "version_prompt": hash_contenu(systeme)[:12]}
            )
            try:
                reponse = self._client.chat.completions.create(
                    model=self.modele,
                    messages=[
                        {"role": "system", "content": systeme},
                        {"role": "user", "content": question},
                    ],
                )
                if reponse.usage is not None:
                    span.set_attributes(
                        {
                            "gen_ai.usage.input_tokens": reponse.usage.prompt_tokens,
                            "gen_ai.usage.output_tokens": reponse.usage.completion_tokens,
                        }
                    )
                return reponse.choices[0].message.content or ""
            except (OpenAIError, ClientAuthenticationError, IndexError) as exc:
                raise ErreurLLM(f"erreur du fournisseur ou réponse mal formée : {exc!r}") from exc
