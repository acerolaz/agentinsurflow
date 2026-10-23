"""Modèle du domaine : état du dossier et sections produites par les agents (dataclasses gelées)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Section = Literal[
    "dossier", "pieces", "risque", "sources", "fiche", "prime", "validation", "pilotage"
]
NomAgent = Literal["pieces", "analyste", "redacteur", "actuaire"]
# La cause tracée porte un suffixe : « garde_fou:GF2 », « garde_fou:entree:prompt_injection ».
Cause = Literal[
    "limite", "not_found", "garde_fou", "llm_ko", "budget", "erreur", "pieces_incompletes", "duree"
]


@dataclass(frozen=True)
class Pieces:
    statut: Literal["complet", "incomplet"]
    manquantes: tuple[str, ...]
    note: str


@dataclass(frozen=True)
class Risque:
    score: int
    classe: Literal["acceptable", "refus", "limite"]
    regle_ids: tuple[str, ...]
    version_bareme: str
    note: str


@dataclass(frozen=True)
class Fiche:
    """Mêmes champs que la `Fiche` du serveur MCP."""

    decision: Literal["ACCEPTE", "REFUSE", "REVUE_HUMAINE"]
    contrat_type: str
    score: float
    version_bareme: str
    regle_ids: tuple[str, ...]
    motifs: tuple[str, ...]
    citations: tuple[str, ...]


@dataclass(frozen=True)
class Prime:
    prime_ttc_annuelle: str
    prime_mensuelle: str
    version_formule: str
    explication: str


@dataclass(frozen=True)
class Rapport:
    agent: NomAgent
    section: dict[Section, object]
    mode: Literal["llm", "repli"]
    cause: str | None
    version_prompt: str


@dataclass(frozen=True)
class EtatDossier:
    numero_contrat: str
    dossier: dict[str, object] | None = None
    observations: str | None = None
    pieces: Pieces | None = None
    risque: Risque | None = None
    sources: tuple[dict[str, object], ...] | None = None
    fiche: Fiche | None = None
    prime: Prime | None = None
    validation: dict[str, object] | None = None
    cause: str | None = None
    entree_bloquee: str | None = None
    tentative: int = 1
    tours: tuple[dict[str, object], ...] = field(default=())
