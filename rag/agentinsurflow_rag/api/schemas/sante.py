from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .corpus import DTO


class CorpusSante(DTO):
    instantane_sha256: str | None = Field(description="dernier instantané ingéré")
    chunks: int = Field(description="chunks des versions courantes ; 0 avant la 1re ingestion")


class Sante(BaseModel):
    statut: Literal["ok"] = "ok"
    version: str = Field(description="SHA du commit de l'image")
    release: str = Field(description="vX.Y.Z ; en staging, la release candidate")
    manifeste: str = Field(description="X.Y.Z-build.N : modèle, prompts et golden dataset évalués")
    environnement: str
    corpus: CorpusSante | None = Field(description="null si la base est injoignable ou non migrée")
