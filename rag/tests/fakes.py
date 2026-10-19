"""Doublures des ports du domaine : les tests ne simulent que les ports, jamais l'infrastructure."""

from __future__ import annotations

from agentinsurflow_rag.domain.ports import ErreurLLM


class FakeLLM:
    """LLM scripté : rend ``texte``, ou lève ``erreur``. Garde la trace des appels."""

    def __init__(self, texte: str = "Réponse simulée.", *, erreur: ErreurLLM | None = None) -> None:
        self.texte, self.erreur, self.modele = texte, erreur, "fake"
        self.appels: list[tuple[str, str]] = []

    def completer(self, systeme: str, question: str) -> str:
        self.appels.append((systeme, question))
        if self.erreur:
            raise self.erreur
        return self.texte
