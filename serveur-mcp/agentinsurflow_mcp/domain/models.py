"""Entités du domaine : l'appelant authentifié et les erreurs d'outil."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Literal

Agent = Literal["orchestrateur", "pieces", "analyste", "redacteur", "actuaire"]

UNAUTHORIZED_TOOL = "UNAUTHORIZED_TOOL"
NOT_FOUND_IN_CORPUS = "NOT_FOUND_IN_CORPUS"
CONTRAT_INTROUVABLE = "CONTRAT_INTROUVABLE"
DOSSIERS_INDISPONIBLES = "DOSSIERS_INDISPONIBLES"
ARGUMENTS_INVALIDES = "ARGUMENTS_INVALIDES"
CALCUL_INDISPONIBLE = "CALCUL_INDISPONIBLE"
DONNEE_HORS_BAREME = "DONNEE_HORS_BAREME"


@dataclass(frozen=True)
class Appelant:
    """Le jeton validé : gestionnaire (``oid``), agent (``azp``) et rôles d'app."""

    oid: str
    azp: str
    agent: Agent | None  # None : azp inconnu, aucun outil
    roles: frozenset[str]
    jeton: str = field(repr=False)  # assertion pour l'échange OBO vers les backends


class ErreurOutil(Exception):
    """Échec métier d'un outil : le client reçoit ``isError`` et ce ``code`` stable."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Fiche:
    """La fiche d'un brouillon (mêmes champs que ``FicheBrouillon`` d'underwriting-admin)."""

    decision: Literal["ACCEPTE", "REFUSE", "REVUE_HUMAINE"]
    contrat_type: str
    score: float
    version_bareme: str
    regle_ids: list[str]
    motifs: list[str]
    citations: list[str]


@dataclass(frozen=True)
class PrimeBrouillon:
    prime_ttc: float
    periodicite: Literal["mensuelle", "annuelle"]
    date_effet: datetime.date
