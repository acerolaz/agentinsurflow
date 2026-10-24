"""Configuration Entra et gateway du cluster (variables d'environnement, jamais de valeur codée)."""

from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigCluster(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    azure_tenant_id: str = ""
    gateway_url: str = "http://localhost:8000"  # D22 : MCP et LLM passent par la gateway
    mcp_api_client_id: str = ""
    llm_audience: str = ""  # api://<appId de agentinsurflow-llm>
    # application du cluster (premier saut OBO) puis une application par agent
    insurflow_cluster_client_id: str = ""
    insurflow_agent_orchestrateur_client_id: str = ""
    insurflow_agent_pieces_client_id: str = ""
    insurflow_agent_analyste_client_id: str = ""
    insurflow_agent_redacteur_client_id: str = ""
    insurflow_agent_actuaire_client_id: str = ""
    insurflow_client_secret: SecretStr | None = None  # 🔒 .env local seulement
    azure_uami_client_id: str | None = None  # identité managée fédérée (Azure)
    telemetrie_audience: str = (
        ""  # api://<appId underwriting> : posée en Azure (export OTLP avec jeton)
    )
    insurflow_llm_actif: bool = True
    insurflow_llm_delai_s: float = 30
    # P24 (ouverte) : mêmes pièces exigées pour toute formule, séparées par des virgules
    insurflow_pieces_exigees: str = "releve_information,permis"

    def pieces_exigees(self) -> tuple[str, ...]:
        return tuple(p.strip() for p in self.insurflow_pieces_exigees.split(",") if p.strip())

    def client_agent(self, agent: str) -> str:
        return getattr(self, f"insurflow_agent_{agent}_client_id", "")
