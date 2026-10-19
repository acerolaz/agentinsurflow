"""Ports du domaine (repris de Kaldera, ``llm.py``) : le domaine ne connaît que ces interfaces."""

from __future__ import annotations

from typing import Protocol


class ErreurLLM(Exception):
    """Le LLM n'a pas répondu à temps, ou le fournisseur a renvoyé une erreur."""


class ErreurEmbeddings(Exception):
    """Le modèle d'embeddings n'a pas répondu, ou le fournisseur a renvoyé une erreur."""


class ClientLLM(Protocol):
    modele: str

    def completer(self, systeme: str, question: str) -> str: ...


class ClientEmbeddings(Protocol):
    modele: str

    def vectoriser(self, textes: list[str]) -> list[list[float]]: ...
