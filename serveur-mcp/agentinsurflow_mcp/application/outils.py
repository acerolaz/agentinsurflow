"""Cas d'usage des outils de lecture : jeton OBO de la cible, puis appel du port."""

from __future__ import annotations

from typing import Any

from ..domain.models import Appelant
from ..domain.ports import CorpusPort, DossiersPort, JetonsPort


async def search_rag(
    appelant: Appelant,
    jetons: JetonsPort,
    corpus: CorpusPort,
    question: str,
    top_k: int | None = None,
) -> dict[str, Any]:
    jeton = await jetons.obo(appelant, "rag")
    return await corpus.chercher(jeton, question, top_k)


async def get_contrat(
    appelant: Appelant, jetons: JetonsPort, dossiers: DossiersPort, numero_contrat: str
) -> dict[str, Any]:
    jeton = await jetons.obo(appelant, "underwriting")
    return await dossiers.lire_contrat(jeton, numero_contrat)
