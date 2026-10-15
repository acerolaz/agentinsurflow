"""Agent du socle : répond à une question du gestionnaire (squelette du parcours V1).

Ne connaît que le port ``ClientLLM``. Sans LLM joignable, la réponse passe en mode dégradé :
la demande part en revue humaine (dossier-conception-v1.md, K5).
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel

from .llm import ClientLLM, ErreurLLM

SYSTEME = (
    "Tu es l'assistant du gestionnaire back office AgentInsurFlow "
    "(souscription d'assurance auto). Réponds en français, en trois phrases au plus."
)
REPLI = "LLM indisponible : la demande passe en revue humaine."

journal = logging.getLogger(__name__)


class Reponse(BaseModel):
    texte: str
    mode: Literal["llm", "degrade"]
    modele: str | None = None


def repondre(question: str, llm: ClientLLM | None) -> Reponse:
    if llm is None:
        journal.warning("mode dégradé : LLM non configuré")
        return Reponse(texte=REPLI, mode="degrade")
    try:
        return Reponse(texte=llm.completer(SYSTEME, question), mode="llm", modele=llm.modele)
    except ErreurLLM as exc:
        journal.warning("mode dégradé : %s", exc)
        return Reponse(texte=REPLI, mode="degrade", modele=llm.modele)
