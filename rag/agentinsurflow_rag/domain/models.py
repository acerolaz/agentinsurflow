"""Entités du domaine (dataclasses) ; l'API les expose par ses propres DTO."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal


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
class Reponse:
    texte: str
    mode: Literal["llm", "degrade"]
    modele: str | None = None
