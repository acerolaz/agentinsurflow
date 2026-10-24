"""Fakes des ports du cluster pour les TU : aucun I/O, aucun LLM."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agentinsurflow_cluster.domain.models import NomAgent, Rapport
from agentinsurflow_cluster.domain.ports import ErreurOutil
from agentinsurflow_cluster.domain.reglages import ReglageAgent

# Valeurs initiales du § 3 de la spec, construites sans lire agents.toml (TU : aucun I/O)
REGLAGES: dict[NomAgent, ReglageAgent] = {
    "pieces": ReglageAgent("gpt-4.1-mini", 0.0, 400, 1.5, "pieces.md"),
    "analyste": ReglageAgent("gpt-4.1-mini", 0.0, 400, 2.0, "analyste.md"),
    "redacteur": ReglageAgent("gpt-4.1-mini", 0.2, 1200, 8.0, "redacteur.md"),
    "actuaire": ReglageAgent("gpt-4.1-mini", 0.0, 400, 1.5, "actuaire.md"),
}

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


CONTRAT = {
    "numero_contrat": "C-1",
    "formule": "tiers",
    "date_effet": "2026-10-01",
    "observations": "Client fidèle depuis dix ans.",
}


class FakeOutils:
    """`reponses[outil]` : un dict, ou une `ErreurOutil` à lever. Trace (agent, outil)."""

    def __init__(self, **reponses: dict[str, Any] | ErreurOutil) -> None:
        self.reponses: dict[str, dict[str, Any] | ErreurOutil] = {
            "lister_pieces": PIECES_OK,
            "evaluer_risque": RISQUE_ACCEPTABLE,
            "calculer_prime": PRIME,
            "get_contrat": CONTRAT,
            "enregistrer_brouillon": {"ok": True},
            "enregistrer_etat": {"ok": True},
            "update_statut_dossier": {"ok": True},
            **reponses,
        }
        self.appels: list[tuple[str, str, str]] = []
        self.arguments: list[tuple[str, dict[str, Any]]] = []  # (outil, arguments)

    def corps(self, outil: str) -> list[dict[str, Any]]:
        return [a for o, a in self.arguments if o == outil]

    async def appeler(
        self, agent: str, jeton_gestionnaire: str, outil: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        self.appels.append((agent, jeton_gestionnaire, outil))
        self.arguments.append((outil, arguments))
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
    def __init__(
        self,
        sortie: list[str] | None = None,
        entree: list[str] | None = None,
        signal: float = 0.0,
    ) -> None:
        self._signal = signal
        self._sortie = sortie or []
        self._entree = entree or []
        self.textes: list[str] = []
        self.entrees: list[str] = []

    def entree(self, texte: str) -> list[str]:
        self.entrees.append(texte)
        return list(self._entree)

    def signal_injection(self, texte: str) -> float:
        return self._signal

    def sortie(self, texte: str) -> list[str]:
        self.textes.append(texte)
        return list(self._sortie)


class FakeAudit:
    def __init__(self) -> None:
        self.traces: list[tuple[str, Rapport, list[str], int]] = []
        self.signaux: list[float] = []

    async def tracer(
        self,
        numero_contrat: str,
        rapport: Rapport,
        garde_fous: list[str],
        duree_ms: int,
        empreinte_vue: str = "",
        signal_injection: float | None = None,
        empreinte_observations: str = "",
        reglage: ReglageAgent | None = None,
    ) -> None:
        if signal_injection is not None:
            self.signaux.append(signal_injection)
        self.traces.append((numero_contrat, rapport, garde_fous, duree_ms))
