"""Spécification déclarative des quatre agents (bornes du dossier § 4.9)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from agentinsurflow_cluster.domain.models import NomAgent, Section


@dataclass(frozen=True)
class SpecAgent:
    nom: NomAgent
    section: Section
    champ_llm: str  # seul champ de la section rédigé par le LLM
    outils_mcp: frozenset[str]
    delai_s: float
    tours_max: int


SPECS: Mapping[NomAgent, SpecAgent] = {
    "pieces": SpecAgent("pieces", "pieces", "note", frozenset({"lister_pieces"}), 1.5, 2),
    "analyste": SpecAgent("analyste", "risque", "note", frozenset({"evaluer_risque"}), 2.0, 2),
    "redacteur": SpecAgent("redacteur", "fiche", "motifs", frozenset({"search_rag"}), 8.0, 5),
    "actuaire": SpecAgent(
        "actuaire", "prime", "explication", frozenset({"calculer_prime"}), 1.5, 2
    ),
}
