"""Ports simulés du serveur MCP (``rag/tests/fakes.py`` est sur le même ``pythonpath``)."""

from __future__ import annotations

from typing import Any, Literal

from agentinsurflow_mcp.domain.models import Appelant, ErreurOutil


def appelant(agent: Literal["orchestrateur", "redacteur", "actuaire"] = "redacteur") -> Appelant:
    return Appelant("oid-a", "azp-a", agent, frozenset({"Gestionnaire"}), "jeton-entrant")


class FauxJetons:
    def __init__(self, refuse: bool = False) -> None:
        self.refuse = refuse
        self.demandes: list[tuple[str, str]] = []

    async def obo(self, appelant: Appelant, cible: Literal["rag", "underwriting"]) -> str:
        if self.refuse:
            raise ErreurOutil("DOSSIERS_INDISPONIBLES", "OBO refusé")
        self.demandes.append((appelant.jeton, cible))
        return f"obo-{cible}"


class FauxCorpus:
    def __init__(self, erreur: ErreurOutil | None = None) -> None:
        self.erreur = erreur
        self.appels: list[tuple[str, str, int | None]] = []

    async def chercher(self, jeton: str, question: str, top_k: int | None) -> dict[str, Any]:
        self.appels.append((jeton, question, top_k))
        if self.erreur:
            raise self.erreur
        return {"statut": "OK", "resultats": [{"texte": "extrait"}]}


class FauxDossiers:
    def __init__(self, erreur: ErreurOutil | None = None) -> None:
        self.erreur = erreur
        self.appels: list[tuple[str, str]] = []

    async def lire_contrat(self, jeton: str, numero_contrat: str) -> dict[str, Any]:
        self.appels.append((jeton, numero_contrat))
        if self.erreur:
            raise self.erreur
        return {"numero_contrat": numero_contrat}

    async def enregistrer_brouillon(
        self, jeton: str, numero_contrat: str, corps: dict[str, Any]
    ) -> None:
        raise AssertionError("hors tâche 5")

    async def changer_statut(self, jeton: str, numero_contrat: str, corps: dict[str, Any]) -> None:
        raise AssertionError("hors tâche 5")
