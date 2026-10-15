"""Port LLM du socle (repris de Kaldera, ``llm.py``).

Le domaine ne connaît que ``ClientLLM`` ; le SDK ``openai`` n'apparaît que dans l'adaptateur
``AzureLLM``. ``FakeLLM`` sert aux tests : la CI n'appelle jamais Azure OpenAI.
"""

from __future__ import annotations

from typing import Protocol

from openai import AzureOpenAI, OpenAIError
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
    """Le modèle est une configuration, pas du code : tout vient du .env ou de GitHub."""

    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    azure_openai_endpoint: str = ""
    azure_openai_api_key: SecretStr = SecretStr("")
    azure_openai_deployment: str = ""
    llm_delai_s: float = Field(default=20, gt=0)


def charger_config() -> ConfigLLM:
    """Lit l'environnement à chaque appel (pas de cache global) ; remplacée dans les tests."""
    return ConfigLLM()


def fabrique_llm(cfg: ConfigLLM) -> ClientLLM | None:
    """Le ClientLLM, ou None s'il n'est pas configuré (⇒ mode dégradé)."""
    cle = cfg.azure_openai_api_key.get_secret_value()
    if not (
        cfg.azure_openai_endpoint
        and cle
        and cfg.azure_openai_deployment
    ):
        return None
    client = AzureOpenAI(
        azure_endpoint=cfg.azure_openai_endpoint,
        api_key=cle,
        timeout=cfg.llm_delai_s,
        max_retries=0,
    )
    return AzureLLM(client, cfg.azure_openai_deployment)


# ------------------------------------------------------------------ adaptateur Azure


class AzureLLM:
    """Azure OpenAI (SDK ``openai``) derrière le port ClientLLM."""

    def __init__(self, client: AzureOpenAI, deploiement: str) -> None:
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
        except (OpenAIError, IndexError) as exc:
            raise ErreurLLM(f"erreur du fournisseur ou réponse mal formée : {exc!r}") from exc
