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
        self, agent: NomAgent, vue: dict[str, Any], budget_s: float, jeton: str = ""
    ) -> dict[str, Any] | None:
        """Rédige le champ LLM de l'agent à partir de sa ``vue`` ; ``None`` = repli (LLM absent,
        délai dépassé ou sortie invalide).

        ``jeton`` : jeton du gestionnaire, pour l'outil ``search_rag`` du Rédacteur seul.
        Retour, selon l'agent (l'application ne retient que ces clés et contrôle tout) :
        - pieces et analyste : ``{"note": str}`` ; actuaire : ``{"explication": str}`` ;
        - redacteur : ``{"decision": str, "contrat_type": str, "motifs": [str], "citations": [str],
          "sources": [dict]}`` ; ``sources`` = résultats de ``search_rag`` aplatis par le code
          (``doc_id``, ``collection``, ``article``, ``regle_id`` éventuel, ``texte``) ;
        - ``{"erreur": <code>}`` (Rédacteur) si ``search_rag`` a échoué sans rien rapporter
          (``NOT_FOUND_IN_CORPUS``, ``UNAUTHORIZED_TOOL``…).
        """
        ...


class GardeTextePort(Protocol):
    def entree(self, texte: str) -> list[str]:
        """Noms des scanners d'entrée en échec."""
        ...

    def signal_injection(self, texte: str) -> float:
        """Score du modèle d'injection (0 à 1) : un signal journalisé, jamais bloquant."""
        ...

    def sortie(self, texte: str) -> list[str]:
        """Noms des scanners de sortie en échec."""
        ...


class AuditPort(Protocol):
    async def tracer(
        self,
        numero_contrat: str,
        rapport: Rapport,
        garde_fous: list[str],
        duree_ms: int,
        empreinte_vue: str = "",
        signal_injection: float | None = None,
    ) -> None:
        """``empreinte_vue`` : SHA-256 de la vue de l'agent (jamais son contenu) ;
        ``signal_injection`` : score seul du modèle d'injection (jamais le texte)."""
        ...
