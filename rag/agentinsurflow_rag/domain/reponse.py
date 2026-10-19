"""Règles de l'agent (spec §4.2) : message de refus, citations lues dans la réponse, contexte.

Fonctions pures, bibliothèque standard seulement.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from .corpus import normaliser_numero
from .models import Extrait, VueContrat

MESSAGE_REFUS = (
    "Je ne trouve pas la réponse dans le corpus (Code des assurances, assurance auto) : "
    "je ne réponds pas sans source."
)
ABSTENTION = "NOT_FOUND_IN_CORPUS"
_CITATION = re.compile(r"\[\s*([LRAD])\s*\.?\s*(\d+(?:-\d+)+)\s*\]", re.IGNORECASE)

# Champs de la vue minimisée donnés au LLM : aucun identifiant de personne (RGPD)
CHAMPS_CONTRAT = (
    "tranche_age",
    "anciennete_permis_ans",
    "departement",
    "crm_bonus_malus",
    "nb_sinistres",
    "suspensions",
    "resiliations",
    "formule",
)


def est_abstention(texte: str) -> bool:
    """Verrou ② : le LLM dit lui-même que les extraits ne suffisent pas."""
    return ABSTENTION in texte


def articles_cites(texte: str) -> list[str]:
    """Numéros cités entre crochets (« [L211-1] »), normalisés, sans doublon, dans l'ordre."""
    vus: dict[str, None] = {}
    for lettre, numero in _CITATION.findall(texte):
        vus.setdefault(normaliser_numero(lettre + numero), None)
    return list(vus)


def contexte(question: str, extraits: Sequence[Extrait], contrat: VueContrat | None) -> str:
    """Message envoyé au LLM : les extraits numérotés par article, le dossier, puis la question."""
    lignes = ["Extraits du Code des assurances :"]
    lignes += [f"[{e.citation.article}] {e.texte}" for e in extraits]
    if contrat is not None:
        lignes += ["", "Dossier du contrat (vue minimisée) :"]
        lignes += [f"- {champ} : {getattr(contrat, champ)}" for champ in CHAMPS_CONTRAT]
    lignes += ["", f"Question : {question}"]
    return "\n".join(lignes)
