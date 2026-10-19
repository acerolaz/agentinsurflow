"""Unitaires — l'agent à trois verrous (spec §4.2) : porte, abstention, contrôle de citation.

Ports simulés seulement (FakeLLM) ; les extraits et la vue du contrat sont des entités du domaine.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from agentinsurflow_rag.application.use_cases.repondre import REPLI, SYSTEME, repondre
from agentinsurflow_rag.domain.models import (
    CitationRag,
    CitationSql,
    Extrait,
    ResultatRecherche,
    VueContrat,
)
from agentinsurflow_rag.domain.ports import ErreurLLM
from agentinsurflow_rag.domain.reponse import MESSAGE_REFUS, articles_cites, contexte
from fakes import FakeLLM


def _extrait(article: str, chunk_id: int, texte: str = "Texte de l'article.") -> Extrait:
    citation = CitationRag(
        f"LEGIARTI_{article}", "v1", article, "textes_reglementaires", date(2003, 1, 1),
        f"https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI_{article}", chunk_id,
    )  # fmt: skip
    return Extrait(citation, texte, 0.8, 0.03)


OK = ResultatRecherche("OK", 0.4, [_extrait("L211-1", 1), _extrait("A121-1", 2)], 0.8)
REFUS = ResultatRecherche("NOT_FOUND_IN_CORPUS", 0.4, [], 0.2)
CONTRAT = VueContrat(
    numero_contrat="AIF-2026-0001",
    tranche_age="25-34",
    anciennete_permis_ans=6,
    departement="69",
    crm_bonus_malus=0.85,
    nb_sinistres=1,
    suspensions=0,
    resiliations=0,
    formule="tous risques",
    mis_a_jour=datetime(2026, 9, 1, tzinfo=UTC),
)


def test_sous_la_porte_refus_sans_appel_llm() -> None:
    llm = FakeLLM("Oui [L211-1].")
    reponse = repondre("Question hors corpus", REFUS, llm)
    assert llm.appels == []
    assert (reponse.statut, reponse.mode, reponse.texte) == (
        "NOT_FOUND_IN_CORPUS",
        "refus",
        MESSAGE_REFUS,
    )
    assert (reponse.citations, reponse.verrou) == ([], 1)


def test_abstention_du_llm_refus() -> None:
    reponse = repondre("Question", OK, FakeLLM("NOT_FOUND_IN_CORPUS"))
    assert (reponse.statut, reponse.texte, reponse.verrou) == (
        "NOT_FOUND_IN_CORPUS",
        MESSAGE_REFUS,
        2,
    )
    assert reponse.modele == "fake"


def test_reponse_sans_citation_refusee() -> None:
    reponse = repondre("Question", OK, FakeLLM("Oui, c'est obligatoire."))
    assert (reponse.statut, reponse.verrou) == ("NOT_FOUND_IN_CORPUS", 3)


def test_citation_inventee_refusee() -> None:
    reponse = repondre("Question", OK, FakeLLM("Oui [L999-9]."))
    assert (reponse.statut, reponse.verrou) == ("NOT_FOUND_IN_CORPUS", 3)


def test_reponse_citee_ne_rend_que_les_extraits_cites() -> None:
    reponse = repondre("Question", OK, FakeLLM("L'assurance est obligatoire [L211-1]."))
    assert (reponse.statut, reponse.mode, reponse.verrou) == ("OK", "llm", None)
    assert [c.article for c in reponse.citations if isinstance(c, CitationRag)] == ["L211-1"]
    assert reponse.texte == "L'assurance est obligatoire [L211-1]."


def test_prompt_systeme_et_extraits_envoyes_au_llm() -> None:
    llm = FakeLLM("Oui [A121-1].")
    repondre("Que dit le bonus malus ?", OK, llm)
    ((systeme, message),) = llm.appels
    assert systeme == SYSTEME and "NOT_FOUND_IN_CORPUS" in SYSTEME
    assert "[L211-1] Texte de l'article." in message and "[A121-1]" in message
    assert message.rstrip().endswith("Question : Que dit le bonus malus ?")


def test_contrat_ajoute_au_contexte_et_cite() -> None:
    llm = FakeLLM("Le coefficient s'applique [A121-1].")
    reponse = repondre("Mon bonus ?", OK, llm, CONTRAT)
    assert "crm_bonus_malus : 0.85" in llm.appels[0][1]
    assert (
        CitationSql("vue_contrat_minimisee", "AIF-2026-0001", CONTRAT.mis_a_jour)
        in reponse.citations
    )


def test_llm_en_panne_revue_humaine_avec_citations() -> None:
    reponse = repondre("Question", OK, FakeLLM(erreur=ErreurLLM("délai dépassé")), CONTRAT)
    assert (reponse.statut, reponse.mode, reponse.texte) == ("REVUE_HUMAINE", "degrade", REPLI)
    assert len(reponse.citations) == 3  # les 2 extraits + le dossier


def test_sans_llm_configure_revue_humaine() -> None:
    reponse = repondre("Question", OK, None)
    assert (reponse.statut, reponse.mode, reponse.modele) == ("REVUE_HUMAINE", "degrade", None)


def test_articles_cites_lus_dans_le_texte() -> None:
    assert articles_cites("Voir [L211-1] et [R. 211-45], pas L211-2 ni [L211].") == [
        "L211-1",
        "R211-45",
    ]


def test_contexte_sans_contrat_n_expose_aucun_dossier() -> None:
    assert "Dossier" not in contexte("Q ?", OK.resultats, None)
