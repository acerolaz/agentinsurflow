"""Entités du domaine : l'appelant authentifié et les erreurs d'outil."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Agent = Literal["orchestrateur", "redacteur", "actuaire"]

UNAUTHORIZED_TOOL = "UNAUTHORIZED_TOOL"
NOT_FOUND_IN_CORPUS = "NOT_FOUND_IN_CORPUS"
CONTRAT_INTROUVABLE = "CONTRAT_INTROUVABLE"
DOSSIERS_INDISPONIBLES = "DOSSIERS_INDISPONIBLES"
ARGUMENTS_INVALIDES = "ARGUMENTS_INVALIDES"


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
