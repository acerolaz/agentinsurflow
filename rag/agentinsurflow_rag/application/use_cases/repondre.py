"""Agent RAG à trois verrous (spec §4.2) : il répond à partir des extraits cités, ou refuse.

① porte de pertinence (déjà jugée par la recherche) : sous la porte, aucun appel au LLM ;
② abstention du LLM (``NOT_FOUND_IN_CORPUS``) ; ③ au moins une citation parmi les extraits.
Sans LLM joignable : mode dégradé du sprint 2, la demande part en revue humaine (K5), avec les
citations trouvées. Synchrone (le SDK du LLM l'est) : la route l'appelle hors de la boucle.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ...domain.models import CitationRag, CitationSql, Reponse, ResultatRecherche, VueContrat
from ...domain.ports import ClientLLM, ErreurLLM
from ...domain.reponse import MESSAGE_REFUS, articles_cites, contexte, est_abstention

# Prompt versionné à part : le modifier déclenche les évaluations (ci-cd.yml, job changements)
SYSTEME = (Path(__file__).parents[2] / "prompts" / "systeme.md").read_text(encoding="utf-8").strip()
REPLI = "LLM indisponible : la demande passe en revue humaine."

journal = logging.getLogger(__name__)


def _refus(verrou: int, modele: str | None) -> Reponse:
    return Reponse(MESSAGE_REFUS, "refus", modele, "NOT_FOUND_IN_CORPUS", [], verrou)


def repondre(
    question: str,
    recherche: ResultatRecherche,
    llm: ClientLLM | None,
    contrat: VueContrat | None = None,
) -> Reponse:
    if recherche.statut != "OK":
        return _refus(1, None)

    citation_sql = (
        [CitationSql("vue_contrat_minimisee", contrat.numero_contrat, contrat.mis_a_jour)]
        if contrat is not None
        else []
    )
    toutes: list[CitationRag | CitationSql] = [e.citation for e in recherche.resultats]
    toutes += citation_sql
    if llm is None:
        journal.warning("mode dégradé : LLM non configuré")
        return Reponse(REPLI, "degrade", None, "REVUE_HUMAINE", toutes)
    try:
        texte = llm.completer(SYSTEME, contexte(question, recherche.resultats, contrat))
    except ErreurLLM as exc:
        journal.warning("mode dégradé : %s", exc)
        return Reponse(REPLI, "degrade", llm.modele, "REVUE_HUMAINE", toutes)

    if est_abstention(texte):
        return _refus(2, llm.modele)
    cites = set(articles_cites(texte))
    extraits_cites = [e.citation for e in recherche.resultats if e.citation.article in cites]
    if not extraits_cites:
        return _refus(3, llm.modele)
    return Reponse(texte, "llm", llm.modele, "OK", [*extraits_cites, *citation_sql])
