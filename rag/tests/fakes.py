"""Doublures des ports du domaine : les tests ne simulent que les ports, jamais l'infrastructure."""

from __future__ import annotations

import hashlib
import math
import re

from agentinsurflow_rag.domain.ports import ErreurEmbeddings, ErreurLLM


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


class FakeEmbeddings:
    """Embeddings déterministes : mots hachés dans ``dim`` dimensions, puis normalisation L2.

    Le cosinus reflète les mots partagés (tests de seuil significatifs) ; jamais le vecteur nul.
    """

    def __init__(self, dim: int = 1536, *, erreur: ErreurEmbeddings | None = None) -> None:
        self.dim, self.erreur, self.modele = dim, erreur, "fake-embeddings"
        self.appels: list[list[str]] = []

    def _vecteur(self, texte: str) -> list[float]:
        vecteur = [0.0] * self.dim
        for mot in re.findall(r"\w+", texte.lower()):
            vecteur[int(hashlib.sha256(mot.encode()).hexdigest(), 16) % self.dim] += 1.0
        if not any(vecteur):
            vecteur[0] = 1.0
        norme = math.sqrt(sum(x * x for x in vecteur))
        return [x / norme for x in vecteur]

    def vectoriser(self, textes: list[str]) -> list[list[float]]:
        self.appels.append(list(textes))
        if self.erreur:
            raise self.erreur
        return [self._vecteur(t) for t in textes]
