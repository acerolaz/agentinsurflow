"""DTO Pydantic de l'API : jamais les entités du domaine (règle hexagonale)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class FicheDto(BaseModel):
    decision: Literal["ACCEPTE", "REFUSE", "REVUE_HUMAINE"]
    contrat_type: str
    score: float
    version_bareme: str
    regle_ids: list[str]
    motifs: list[str]
    citations: list[str]


class PrimeDto(BaseModel):
    prime_ttc_annuelle: str
    prime_mensuelle: str
    version_formule: str
    explication: str


class EtapeDto(BaseModel):
    tour: int
    outil_appele: str
    precondition: str | None
    mode: str


class EvaluationReponse(BaseModel):
    statut: Literal["EN_ANALYSE", "REVUE_HUMAINE"]
    fiche: FicheDto | None
    prime: PrimeDto | None
    message: str | None  # jamais la cause d'une revue humaine
    synthese: list[EtapeDto]


class RevueCorps(BaseModel):
    decision: Literal["ACCEPTE", "REFUSE"]
    validation: Literal["VALIDEE", "CORRIGEE"]
    motif: str = Field(min_length=1, max_length=500)


class RevueReponse(BaseModel):
    statut: Literal["ACCEPTE", "REFUSE"]


class SanteReponse(BaseModel):
    version: str
    prompts: dict[str, str]
    garde_fous: Literal["prets"]
