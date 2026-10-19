from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from ...domain.models import CitationRag, CitationSql, Reponse
from .corpus import DTO, CitationRagDTO


class Question(BaseModel):
    texte: str = Field(
        min_length=1,
        max_length=2000,
        examples=["Que couvre l'assurance obligatoire du véhicule ?"],
    )
    numero_contrat: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9-]{1,40}$",
        description="Facultatif : le dossier est ajouté au contexte (vue minimisée, contrôle BOLA)",
        examples=["AIF-2026-0001"],
    )


class CitationSqlDTO(DTO):
    table: Literal["vue_contrat_minimisee"]
    identifiant: str
    date: datetime


class ReponseDTO(BaseModel):
    texte: str
    mode: Literal["llm", "degrade", "refus"]
    modele: str | None = None
    statut: Literal["OK", "NOT_FOUND_IN_CORPUS", "REVUE_HUMAINE"]
    citations: list[CitationRagDTO | CitationSqlDTO]
    trace_id: str | None = Field(description="Trace OpenTelemetry : GET /api/traces/{trace_id}")

    @classmethod
    def depuis(cls, reponse: Reponse, trace_id: str | None) -> ReponseDTO:
        citations: list[CitationRagDTO | CitationSqlDTO] = [
            CitationRagDTO.model_validate(c)
            if isinstance(c, CitationRag)
            else CitationSqlDTO.model_validate(c)
            for c in reponse.citations
            if isinstance(c, CitationRag | CitationSql)
        ]
        return cls(
            texte=reponse.texte,
            mode=reponse.mode,
            modele=reponse.modele,
            statut=reponse.statut,
            citations=citations,
            trace_id=trace_id,
        )
