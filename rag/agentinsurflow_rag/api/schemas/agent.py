from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ...domain.models import Reponse


class Question(BaseModel):
    texte: str = Field(min_length=1, max_length=2000, examples=["Que couvre la garantie tiers ?"])


class ReponseDTO(BaseModel):
    texte: str
    mode: Literal["llm", "degrade"]
    modele: str | None = None

    @classmethod
    def depuis(cls, reponse: Reponse) -> ReponseDTO:
        return cls(texte=reponse.texte, mode=reponse.mode, modele=reponse.modele)
