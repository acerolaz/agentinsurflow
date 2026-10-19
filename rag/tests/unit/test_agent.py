"""Unitaires — l'agent ne dépend que du port ClientLLM ; le mode dégradé ne perd rien."""

from __future__ import annotations

from agentinsurflow_rag.application.use_cases.repondre import REPLI, SYSTEME, repondre
from agentinsurflow_rag.domain.ports import ErreurLLM
from fakes import FakeLLM


def test_repond_via_le_llm_avec_le_prompt_systeme() -> None:
    llm = FakeLLM("Bonjour.")
    reponse = repondre("Que couvre le tiers ?", llm)
    assert (reponse.texte, reponse.mode, reponse.modele) == ("Bonjour.", "llm", "fake")
    assert llm.appels == [(SYSTEME, "Que couvre le tiers ?")]


def test_sans_llm_configure_passe_en_mode_degrade() -> None:
    reponse = repondre("Question", None)
    assert (reponse.texte, reponse.mode, reponse.modele) == (REPLI, "degrade", None)


def test_erreur_du_llm_passe_en_mode_degrade() -> None:
    reponse = repondre("Question", FakeLLM(erreur=ErreurLLM("délai dépassé")))
    assert (reponse.mode, reponse.modele) == ("degrade", "fake")
