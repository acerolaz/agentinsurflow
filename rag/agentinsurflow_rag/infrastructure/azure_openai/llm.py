"""Adaptateur Azure OpenAI du port ``ClientLLM`` (repris de Kaldera, ``llm.py``).

Le SDK ``openai`` n'apparaît qu'ici. Authentification : la clé si elle est fournie, sinon Entra ID
(``DefaultAzureCredential``) : identité OIDC dans la CI, identité managée dans Container Apps,
``az login`` en local.
"""

from __future__ import annotations

from azure.core.exceptions import ClientAuthenticationError
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import OpenAI, OpenAIError

from ...domain.ports import ClientLLM, ErreurLLM
from .config import SCOPE_ENTRA, ConfigLLM


def fabrique_llm(cfg: ConfigLLM) -> ClientLLM | None:
    """Le ClientLLM, ou None s'il n'est pas configuré (⇒ mode dégradé)."""
    if not (cfg.azure_openai_endpoint and cfg.azure_openai_deployment):
        return None
    cle = cfg.azure_openai_api_key.get_secret_value()
    # API v1 d'Azure OpenAI : client OpenAI standard, sans version d'API à gérer
    client = OpenAI(
        base_url=f"{cfg.azure_openai_endpoint.rstrip('/').removesuffix('/openai/v1')}/openai/v1/",
        api_key=cle or get_bearer_token_provider(DefaultAzureCredential(), SCOPE_ENTRA),
        timeout=cfg.llm_delai_s,
        max_retries=0,
    )
    return AzureLLM(client, cfg.azure_openai_deployment)


class AzureLLM:
    """Azure OpenAI (SDK ``openai``, API v1) derrière le port ClientLLM."""

    def __init__(self, client: OpenAI, deploiement: str) -> None:
        self._client, self.modele = client, deploiement

    def completer(self, systeme: str, question: str) -> str:
        try:
            reponse = self._client.chat.completions.create(
                model=self.modele,
                messages=[
                    {"role": "system", "content": systeme},
                    {"role": "user", "content": question},
                ],
            )
            return reponse.choices[0].message.content or ""
        except (OpenAIError, ClientAuthenticationError, IndexError) as exc:
            raise ErreurLLM(f"erreur du fournisseur ou réponse mal formée : {exc!r}") from exc
