"""Ports du domaine : ce que le cluster attend de l'extérieur (outils MCP, rédaction, garde, audit).

Stdlib seulement : les adapters (``infrastructure/``) les réalisent, jamais l'inverse.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol

from agentinsurflow_cluster.domain.models import NomAgent, Rapport

AgentOuOrchestrateur = NomAgent | Literal["orchestrateur"]


class ErreurOutil(Exception):
    """Échec d'un outil MCP ; ``code`` est celui du serveur (``UNAUTHORIZED_TOOL``,
    ``NOT_FOUND_IN_CORPUS``, ``DONNEE_HORS_BAREME``…) ou un code local (``OBO_*``, ``MCP_*``)."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class OutilsPort(Protocol):
    async def appeler(
        self,
        agent: AgentOuOrchestrateur,
        jeton_gestionnaire: str,
        outil: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Lève ``ErreurOutil(code)`` si l'outil est refusé ou en échec."""
        ...


class RedactionPort(Protocol):
    async def rediger(
        self, agent: NomAgent, vue: dict[str, Any], budget_s: float
    ) -> dict[str, Any] | None:
        """``None`` = repli : LLM absent, délai dépassé ou sortie invalide."""
        ...


class GardeTextePort(Protocol):
    def entree(self, texte: str) -> list[str]:
        """Noms des scanners d'entrée en échec."""
        ...

    def sortie(self, texte: str) -> list[str]:
        """Noms des scanners de sortie en échec."""
        ...


class AuditPort(Protocol):
    async def tracer(
        self, numero_contrat: str, rapport: Rapport, garde_fous: list[str], duree_ms: int
    ) -> None: ...
