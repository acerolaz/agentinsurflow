"""Entités du domaine (dataclasses) ; l'API les expose par ses propres DTO."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal


@dataclass(frozen=True)
class Appelant:
    """L'utilisateur ou le service authentifié : identifiant Entra (``oid``) et rôles d'app."""

    oid: str
    roles: frozenset[str]


@dataclass(frozen=True)
class ArticlePropre:
    """Un article nettoyé, prêt à indexer (une version d'un article du Code des assurances)."""

    doc_id: str
    version: str
    article: str  # numéro normalisé, ex. L211-1
    date_debut: date | None
    etat: str
    url_source: str
    texte: str
    hash_contenu: str


@dataclass(frozen=True)
class Rejet:
    """Un article écarté du lot, avec sa raison (partiel:<champ>, vide, trop_court…)."""

    doc_id: str | None
    raison: str


@dataclass(frozen=True)
class QuasiDoublon:
    """Deux articles distincts au contenu presque identique (cosinus > 0,95) : signalé, gardé."""

    doc_id: str
    proche_de: str
    score: float


@dataclass
class RapportIngestion:
    """Rapport d'un lot (spec §3.2 ⑩) ; ``id`` = la ligne journalisée dans ``ingestion``."""

    lus: int = 0
    inseres: int = 0
    inchanges: int = 0
    nouvelles_versions: int = 0
    rejets: list[Rejet] = field(default_factory=list)
    quasi_doublons: list[QuasiDoublon] = field(default_factory=list)
    duree_s: float = 0.0
    id: int | None = None


@dataclass(frozen=True)
class IngestionJournalisee:
    id: int
    instantane_sha256: str
    recu_le: datetime
    rapport: dict[str, Any]


@dataclass(frozen=True)
class EtatCorpus:
    """Pour ``/health`` : dernier instantané ingéré et nombre de chunks des versions courantes."""

    instantane_sha256: str | None
    chunks: int


@dataclass(frozen=True)
class CitationRag:
    """De quoi remonter à la source : Légifrance (``url_source``) et le chunk cité."""

    doc_id: str
    version: str
    article: str
    collection: str
    date_debut: date | None
    url_source: str
    chunk_id: int


@dataclass(frozen=True)
class Extrait:
    citation: CitationRag
    texte: str
    cosinus: float | None  # None pour une référence exacte (recherche directe sur l'article)
    score_rrf: float


@dataclass(frozen=True)
class ResultatRecherche:
    statut: Literal["OK", "NOT_FOUND_IN_CORPUS"]
    seuil: float
    resultats: list[Extrait]
    cosinus_max: float | None = None
    reference_exacte: bool = False


@dataclass(frozen=True)
class VersionDocument:
    version: str
    etat: str
    date_debut: date | None
    hash_contenu: str
    obsolete: bool
    ingere_le: datetime
    url_source: str


@dataclass(frozen=True)
class ChunkDocument:
    id: int
    version: str
    article: str
    ordre: int
    texte: str


@dataclass(frozen=True)
class DocumentTrace:
    """Traçabilité d'un article : toutes ses versions et leurs chunks (sans les vecteurs)."""

    doc_id: str
    collection: str
    versions: list[VersionDocument]
    chunks: list[ChunkDocument]


@dataclass(frozen=True)
class VueContrat:
    """Vue minimisée d'un contrat (D39), lue chez underwriting-admin après son contrôle BOLA.

    Aucun nom, aucune adresse, aucun numéro de permis (RGPD, minimisation).
    """

    numero_contrat: str
    tranche_age: str
    anciennete_permis_ans: int
    departement: str
    crm_bonus_malus: float
    nb_sinistres: int
    suspensions: int
    resiliations: int
    formule: str
    mis_a_jour: datetime


@dataclass(frozen=True)
class CitationSql:
    """La réponse s'appuie sur le dossier : quelle vue, quel contrat, à quelle date."""

    table: Literal["vue_contrat_minimisee"]
    identifiant: str
    date: datetime


@dataclass(frozen=True)
class Reponse:
    """Réponse de l'agent : citée (OK), refusée (NOT_FOUND_IN_CORPUS) ou en revue humaine.

    ``verrou`` dit lequel des trois verrous a refusé (1 porte, 2 abstention, 3 citation).
    """

    texte: str
    mode: Literal["llm", "degrade", "refus"]
    modele: str | None = None
    statut: Literal["OK", "NOT_FOUND_IN_CORPUS", "REVUE_HUMAINE"] = "OK"
    citations: list[CitationRag | CitationSql] = field(default_factory=list)
    verrou: int | None = None
