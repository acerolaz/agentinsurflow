"""Ports du domaine : ce que les outils attendent de l'extérieur (jetons, corpus, dossiers)."""

from __future__ import annotations

from typing import Any, Literal, Protocol

from .models import Appelant


class JetonsPort(Protocol):
    async def obo(self, appelant: Appelant, cible: Literal["rag", "underwriting"]) -> str:
        """Jeton On-Behalf-Of pour ``cible`` ; lève ``ErreurOutil(DOSSIERS_INDISPONIBLES)``."""
        ...


class CorpusPort(Protocol):
    async def chercher(self, jeton: str, question: str, top_k: int | None) -> dict[str, Any]:
        """``ResultatRechercheDTO`` de rag ; ``NOT_FOUND_IN_CORPUS`` lève ``ErreurOutil``."""
        ...


class DossiersPort(Protocol):
    async def lire_contrat(self, jeton: str, numero_contrat: str) -> dict[str, Any]: ...

    async def enregistrer_brouillon(
        self, jeton: str, numero_contrat: str, corps: dict[str, Any]
    ) -> None: ...

    async def changer_statut(
        self, jeton: str, numero_contrat: str, corps: dict[str, Any]
    ) -> None: ...


class CalculateurPort(Protocol):
    async def evaluer(self, faits: dict[str, Any]) -> dict[str, Any]:
        """Évalue le risque ; lève ``ErreurOutil(DONNEE_HORS_BAREME | CALCUL_INDISPONIBLE)``."""
        ...

    async def calculer(self, faits: dict[str, Any]) -> dict[str, Any]:
        """Calcule la prime ; mêmes erreurs que ``evaluer``."""
        ...
