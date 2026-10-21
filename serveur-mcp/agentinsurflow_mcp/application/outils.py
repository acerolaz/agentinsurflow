"""Cas d'usage des outils : jeton OBO de la cible, puis appel du port."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Literal

from ..domain.models import Appelant, Fiche, PrimeBrouillon
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


async def enregistrer_brouillon(
    appelant: Appelant,
    jetons: JetonsPort,
    dossiers: DossiersPort,
    numero_contrat: str,
    fiche: Fiche,
    prime: PrimeBrouillon | None = None,
) -> dict[str, Any]:
    corps = {
        "fiche": asdict(fiche),
        "prime": None
        if prime is None
        else {**asdict(prime), "date_effet": prime.date_effet.isoformat()},
    }
    jeton = await jetons.obo(appelant, "underwriting")
    await dossiers.enregistrer_brouillon(jeton, numero_contrat, corps)
    return {"ecrit": True}


async def update_statut_dossier(
    appelant: Appelant,
    jetons: JetonsPort,
    dossiers: DossiersPort,
    numero_contrat: str,
    statut: Literal["EN_ANALYSE", "REVUE_HUMAINE", "ACCEPTE", "REFUSE"],
    validation: Literal["VALIDEE", "CORRIGEE"] | None = None,
) -> dict[str, Any]:
    jeton = await jetons.obo(appelant, "underwriting")
    await dossiers.changer_statut(
        jeton, numero_contrat, {"statut": statut, "validation": validation}
    )
    return {"ecrit": True}
