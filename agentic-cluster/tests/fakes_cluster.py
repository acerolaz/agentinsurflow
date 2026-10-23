"""Fakes des ports du cluster pour les TU : aucun I/O, aucun LLM."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agentinsurflow_cluster.domain.models import NomAgent, Rapport
from agentinsurflow_cluster.domain.ports import ErreurOutil

PIECES_OK = {
    "pieces": [
        {"type": "permis", "date_emission": "2026-09-01"},
        {"type": "releve_information", "date_emission": "2026-09-01"},
    ]
}
RISQUE_ACCEPTABLE = {
    "classe": "acceptable",
    "score": 3,
    "regles": [{"regle_id": "R05_CRM"}],
    "version_bareme": "bareme-2026.10-v1",
}
RISQUE_REFUS = {
    "classe": "refus",
    "score": 12,
    "regles": [{"regle_id": "R01_SUSPENSION"}],
    "version_bareme": "bareme-2026.10-v1",
}
PRIME = {
    "version_formule": "tarif-v1",
    "prime_ttc_annuelle": "600.00",
    "prime_mensuelle": "50.00",
}


class FakeOutils:
    """`reponses[outil]` : un dict, ou une `ErreurOutil` à lever. Trace (agent, outil)."""

    def __init__(self, **reponses: dict[str, Any] | ErreurOutil) -> None:
        self.reponses: dict[str, dict[str, Any] | ErreurOutil] = {
            "lister_pieces": PIECES_OK,
            "evaluer_risque": RISQUE_ACCEPTABLE,
            "calculer_prime": PRIME,
            **reponses,
        }
        self.appels: list[tuple[str, str, str]] = []

    async def appeler(
        self, agent: str, jeton_gestionnaire: str, outil: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        self.appels.append((agent, jeton_gestionnaire, outil))
        r = self.reponses[outil]
        if isinstance(r, ErreurOutil):
            raise r
        return r


SOURCE_NOTICE = {"doc_id": "tiers", "collection": "notices_produits", "texte": "Notice tiers."}
SOURCE_REGLE = {
    "doc_id": "refus-suspension",
    "collection": "regles",
    "regle_id": "R01_SUSPENSION",
    "texte": "Suspension : refus.",
}


def redaction_fidele(agent: NomAgent, vue: dict[str, Any]) -> dict[str, Any]:
    """Ce qu'un LLM sage rédigerait à partir de la vue."""
    if agent == "pieces":
        return {"note": f"Pièces manquantes : {', '.join(vue['manquantes'])}."}
    if agent == "analyste":
        regles = ", ".join(vue["regle_ids"])
        return {
            "note": f"Classe {vue['classe']}, score {vue['score']}, règles {regles}, "
            f"barème {vue['version_bareme']}."
        }
    if agent == "actuaire":
        return {"explication": f"Prime calculée avec {vue['version_formule']}."}
    if vue["classe"] == "refus":
        return {
            "decision": "REFUSE",
            "contrat_type": "tiers",
            "motifs": ["Le barème conduit au refus."],
            "citations": ["refus-suspension"],
            "sources": [SOURCE_REGLE],
        }
    return {
        "decision": "ACCEPTE",
        "contrat_type": "tiers",
        "motifs": ["Le dossier est acceptable."],
        "citations": ["tiers"],
        "sources": [SOURCE_NOTICE],
    }


class FakeRedaction:
    """`scenario(agent, vue)` rend la sortie (ou `None` = lent). Trace les vues reçues."""

    def __init__(
        self, scenario: Callable[[NomAgent, dict[str, Any]], dict[str, Any] | None] | None = None
    ) -> None:
        self.scenario = scenario or redaction_fidele
        self.appels: list[tuple[NomAgent, dict[str, Any], str]] = []

    async def rediger(
        self, agent: NomAgent, vue: dict[str, Any], budget_s: float, jeton: str = ""
    ) -> dict[str, Any] | None:
        self.appels.append((agent, vue, jeton))
        return self.scenario(agent, vue)


class FakeGarde:
    def __init__(self, sortie: list[str] | None = None) -> None:
        self._sortie = sortie or []
        self.textes: list[str] = []

    def entree(self, texte: str) -> list[str]:
        return []

    def sortie(self, texte: str) -> list[str]:
        self.textes.append(texte)
        return list(self._sortie)


class FakeAudit:
    def __init__(self) -> None:
        self.traces: list[tuple[str, Rapport, list[str], int]] = []

    async def tracer(
        self, numero_contrat: str, rapport: Rapport, garde_fous: list[str], duree_ms: int
    ) -> None:
        self.traces.append((numero_contrat, rapport, garde_fous, duree_ms))
