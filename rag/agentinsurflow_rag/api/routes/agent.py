from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ...application.use_cases.repondre import repondre
from ...domain.ports import ClientLLM
from ...infrastructure.azure_openai.config import charger_config
from ...infrastructure.azure_openai.llm import fabrique_llm
from ..schemas.agent import Question, ReponseDTO

router = APIRouter()


def obtenir_llm() -> ClientLLM | None:
    # ponytail: client recréé à chaque requête (~500/jour) ; au lifespan si la latence compte
    return fabrique_llm(charger_config())


@router.post("/api/agent")
def interroger_agent(
    q: Question, llm: Annotated[ClientLLM | None, Depends(obtenir_llm)]
) -> ReponseDTO:
    return ReponseDTO.depuis(repondre(q.texte, llm))
