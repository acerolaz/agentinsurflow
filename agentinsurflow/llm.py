"""Port LLM du socle (repris de Kaldera, ``llm.py``).

Le domaine ne connaît que ``ClientLLM`` ; le SDK ``openai`` n'apparaît que dans l'adaptateur
``AzureLLM``. ``FakeLLM`` sert aux tests unitaires et d'intégration (aucun appel réel).

Authentification : la clé si elle est fournie, sinon Entra ID (``DefaultAzureCredential``) :
identité OIDC dans la CI, identité managée dans Container Apps, ``az login`` en local.
"""

from __future__ import annotations

from typing import Protocol

from azure.core.exceptions import ClientAuthenticationError
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import OpenAI, OpenAIError
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ErreurLLM(Exception):
    """Le LLM n'a pas répondu à temps, ou le fournisseur a renvoyé une erreur."""


class ClientLLM(Protocol):
    modele: str

    def completer(self, systeme: str, question: str) -> str: ...


# ------------------------------------------------------------------ FakeLLM


class FakeLLM:
    """LLM scripté : rend ``texte``, ou lève ``erreur``. Garde la trace des appels."""

    def __init__(self, texte: str = "Réponse simulée.", *, erreur: ErreurLLM | None = None) -> None:
        self.texte, self.erreur, self.modele = texte, erreur, "fake"
        self.appels: list[tuple[str, str]] = []

    def completer(self, systeme: str, question: str) -> str:
        self.appels.append((systeme, question))
        if self.erreur:
            raise self.erreur
        return self.texte


# ------------------------------------------------------------------ configuration


class ConfigLLM(BaseSettings):
    """Le modèle est une configuration, pas du code : ``llm.env`` (versionné) puis ``.env``."""

    model_config = SettingsConfigDict(
        env_file=("llm.env", ".env"), env_ignore_empty=True, extra="ignore"
    )

    azure_openai_endpoint: str = ""
    azure_openai_api_key: SecretStr = SecretStr("")
    azure_openai_deployment: str = ""
    llm_delai_s: float = Field(default=30, gt=0)  # aligné sur la porte p95 ≤ 30 s (D11)


SCOPE_ENTRA = "https://cognitiveservices.azure.com/.default"


def charger_config() -> ConfigLLM:
    """Lit l'environnement à chaque appel (pas de cache global) ; remplacée dans les tests."""
    return ConfigLLM()


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


# ------------------------------------------------------------------ adaptateur Azure


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
