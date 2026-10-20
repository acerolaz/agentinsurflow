"""DTO du corpus : lots d'ingestion, rapports, extraits, traçabilité (jamais les entités)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ArticleEntrant(BaseModel):
    """Un article tel qu'extrait de Légifrance ; tout est facultatif : un article partiel est
    rejeté avec sa raison, sans faire échouer le lot (spec §3.2 ⑤)."""

    model_config = ConfigDict(extra="ignore")

    doc_id: str | None = None
    version: str | None = None
    article: str | None = Field(default=None, examples=["L. 211-1"])
    date_debut: str | None = Field(default=None, examples=["2003-01-01"])
    etat: str | None = Field(default=None, examples=["VIGUEUR"])
    texte_html: str | None = None
    url_source: str | None = None


class LotIngestion(BaseModel):
    collection: Literal["textes_reglementaires"]
    instantane_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    instantane_date: date
    articles: list[ArticleEntrant] = Field(min_length=1, max_length=50)

    @field_validator("instantane_date")
    @classmethod
    def _pas_dans_le_futur(cls, jour: date) -> date:
        # +1 jour : la CLI tourne à Paris, déjà « demain » juste après minuit pour le serveur (UTC)
        if jour > datetime.now(UTC).date() + timedelta(days=1):
            raise ValueError("instantane_date ne peut pas être dans le futur")
        return jour


class RejetDTO(DTO):
    doc_id: str | None
    raison: str


class QuasiDoublonDTO(DTO):
    doc_id: str
    proche_de: str
    score: float


class RapportIngestionDTO(DTO):
    id: int
    lus: int
    inseres: int
    inchanges: int
    nouvelles_versions: int
    rejets: list[RejetDTO]
    quasi_doublons: list[QuasiDoublonDTO]
    duree_s: float


class IngestionDTO(DTO):
    id: int
    instantane_sha256: str
    recu_le: datetime
    rapport: dict[str, Any]


class CitationRagDTO(DTO):
    doc_id: str
    version: str
    article: str
    collection: str
    date_debut: date | None
    url_source: str
    chunk_id: int


class ExtraitDTO(DTO):
    citation: CitationRagDTO
    texte: str
    cosinus: float | None
    score_rrf: float


class ResultatRechercheDTO(DTO):
    statut: Literal["OK", "NOT_FOUND_IN_CORPUS"]
    seuil: float
    cosinus_max: float | None
    reference_exacte: bool
    resultats: list[ExtraitDTO]


class VersionDTO(DTO):
    version: str
    etat: str
    date_debut: date | None
    hash_contenu: str
    obsolete: bool
    ingere_le: datetime
    url_source: str
    extrait_le: date


class ChunkDTO(DTO):
    id: int
    version: str
    article: str
    ordre: int
    texte: str


class DocumentDTO(DTO):
    doc_id: str
    collection: str
    versions: list[VersionDTO]
    chunks: list[ChunkDTO]
