"""Configuration du LLM : le modèle est une configuration, pas du code."""

from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigLLM(BaseSettings):
    """``llm.env`` (versionné) puis ``.env``, lus dans le répertoire courant (``rag/``)."""

    model_config = SettingsConfigDict(
        env_file=("llm.env", ".env"), env_ignore_empty=True, extra="ignore"
    )

    azure_openai_endpoint: str = ""
    azure_openai_api_key: SecretStr = SecretStr("")
    azure_openai_deployment: str = ""
    azure_openai_embedding_deployment: str = ""
    llm_delai_s: float = Field(default=30, gt=0)  # aligné sur la porte p95 ≤ 30 s (D11)


SCOPE_ENTRA = "https://cognitiveservices.azure.com/.default"


def charger_config() -> ConfigLLM:
    """Lit l'environnement à chaque appel (pas de cache global) ; remplacée dans les tests."""
    return ConfigLLM()
