"""API REST du socle : ``GET /health`` et ``POST /api/agent`` ; interface = Swagger UI sur ``/``.

Routes minces : elles délèguent à l'agent et rendent des schémas Pydantic.
"""

from __future__ import annotations

from importlib.metadata import version
from typing import Annotated, Literal

from fastapi import Depends, FastAPI
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from . import agent
from .llm import ClientLLM, charger_config, fabrique_llm


class ConfigApp(BaseSettings):
    """Versions gravées dans l'image au build : SHA du commit, release vX.Y.Z, manifeste."""

    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    app_version: str = "dev"
    app_release: str = "dev"
    app_manifeste: str = "dev"
    app_env: str = "local"


class Question(BaseModel):
    texte: str = Field(min_length=1, max_length=2000, examples=["Que couvre la garantie tiers ?"])


class Sante(BaseModel):
    statut: Literal["ok"] = "ok"
    version: str = Field(description="SHA du commit de l'image")
    release: str = Field(description="vX.Y.Z ; en staging, la release candidate")
    manifeste: str = Field(description="X.Y.Z-build.N : modèle, prompts et golden dataset évalués")
    environnement: str


def charger_app() -> ConfigApp:
    return ConfigApp()


def obtenir_llm() -> ClientLLM | None:
    # ponytail: client recréé à chaque requête (~500/jour) ; au lifespan si la latence compte
    return fabrique_llm(charger_config())


app = FastAPI(title="AgentInsurFlow", version=version("agentinsurflow"), docs_url="/")


@app.get("/health")
def sante(cfg: Annotated[ConfigApp, Depends(charger_app)]) -> Sante:
    return Sante(
        version=cfg.app_version,
        release=cfg.app_release,
        manifeste=cfg.app_manifeste,
        environnement=cfg.app_env,
    )


@app.post("/api/agent")
def interroger_agent(
    q: Question, llm: Annotated[ClientLLM | None, Depends(obtenir_llm)]
) -> agent.Reponse:
    return agent.repondre(q.texte, llm)
