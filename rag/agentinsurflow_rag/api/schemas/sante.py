from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Sante(BaseModel):
    statut: Literal["ok"] = "ok"
    version: str = Field(description="SHA du commit de l'image")
    release: str = Field(description="vX.Y.Z ; en staging, la release candidate")
    manifeste: str = Field(description="X.Y.Z-build.N : modèle, prompts et golden dataset évalués")
    environnement: str
