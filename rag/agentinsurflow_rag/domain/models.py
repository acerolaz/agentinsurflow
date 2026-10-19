"""Entités du domaine (dataclasses) ; l'API les expose par ses propres DTO."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Reponse:
    texte: str
    mode: Literal["llm", "degrade"]
    modele: str | None = None
