"""Cas d'usage d'une évaluation : charger, avancer d'un pas, proposer, enregistrer la revue.

Orchestre le domaine (plan, fusion) et les agents ; ne dépend que des ports. Le graphe LangGraph
(``infrastructure/langgraph``) ne fait que chaîner ces fonctions et porter la pause humaine.
Aucune trace ni écriture ne porte les observations du dossier (seules des empreintes, D89).
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, Literal, get_args

from agentinsurflow_cluster.application.agents import Dependances, executer_agent
from agentinsurflow_cluster.application.serialisation import vers_json
from agentinsurflow_cluster.domain.fusion import FusionRefusee, fusionner
from agentinsurflow_cluster.domain.models import (
    EtatDossier,
    Fiche,
    NomAgent,
    Rapport,
    Section,
)
from agentinsurflow_cluster.domain.plan import Appel, precondition, prochaine_etape
from agentinsurflow_cluster.domain.specs import SPECS

ORCHESTRATEUR: Literal["orchestrateur"] = "orchestrateur"
SEUIL_BUDGET_S = 0.3  # en deçà, aucun agent n'a le temps de répondre : revue humaine (« duree »)
MESSAGE_REVUE_HUMAINE = "Ce dossier nécessite une revue humaine."

_AGENT_DE: Mapping[Appel, NomAgent] = {
    "appeler_pieces": "pieces",
    "appeler_analyste_risque": "analyste",
    "appeler_redacteur": "redacteur",
    "appeler_actuaire": "actuaire",
}
# Motif lisible du brouillon de revue humaine : jamais le nom d'un détecteur (R13).
_MOTIFS: Mapping[str, str] = {
    "pieces_incompletes": "Pièces incomplètes : revue humaine requise.",
    "limite": "Dossier à la limite du barème : revue humaine requise.",
    "duree": "Délai d'analyse dépassé : revue humaine requise.",
}


class EvaluationEnAttente(Exception):
    """Une revue du gestionnaire attend déjà pour ce dossier."""


class AucuneRevueEnAttente(Exception):
    """Aucune évaluation n'attend la revue du gestionnaire."""


@dataclass(frozen=True)
class Revue:
    decision: Literal["ACCEPTE", "REFUSE"]
    validation: Literal["VALIDEE", "CORRIGEE"]
    motif: str


async def charger(numero: str, jeton: str, deps: Dependances) -> EtatDossier:
    """``get_contrat`` (orchestrateur) puis garde d'entrée sur les observations."""
    contrat = await deps.outils.appeler(
        ORCHESTRATEUR, jeton, "get_contrat", {"numero_contrat": numero}
    )
    observations = contrat.get("observations") or None
    dossier = {k: v for k, v in contrat.items() if k != "observations"}
    bloquee = None
    if observations:
        codes = await asyncio.to_thread(deps.garde.entree, observations)  # modèles : CPU
        if codes:
            bloquee = f"garde_fou:entree:{codes[0]}"
            await deps.audit.tracer(
                numero, Rapport(ORCHESTRATEUR, {}, "repli", bloquee, ""), codes, 0
            )
    return EtatDossier(numero, dossier=dossier, observations=observations, entree_bloquee=bloquee)


def _etat_a_enregistrer(etat: EtatDossier, statut_parcours: str) -> dict[str, Any]:
    sections = [
        {"section": s, "contenu": vers_json(getattr(etat, s))}
        for s in get_args(Section)
        if getattr(etat, s, None) is not None
    ]
    return {
        "statut_parcours": statut_parcours,
        "tentative": etat.tentative,
        "sections": sections,
        "rapports": vers_json(etat.rapports),
        "tours": vers_json(etat.tours),
    }


async def _enregistrer_etat(
    etat: EtatDossier, statut_parcours: str, jeton: str, deps: Dependances
) -> None:
    await deps.outils.appeler(
        ORCHESTRATEUR,
        jeton,
        "enregistrer_etat",
        {"numero_contrat": etat.numero_contrat, "etat": _etat_a_enregistrer(etat, statut_parcours)},
    )


def termine(etat: EtatDossier) -> bool:
    """Plus d'agent à appeler : proposer au gestionnaire ou orienter vers la revue humaine."""
    return prochaine_etape(etat)[0] not in _AGENT_DE


async def pas(
    etat: EtatDossier, jeton: str, deps: Dependances, ecoule_s: float = 0.0
) -> EtatDossier:
    """Un tour : étape du plan, agent, fusion, ``enregistrer_etat`` (sans effet si terminé)."""
    appel, _ = prochaine_etape(etat)
    nom = _AGENT_DE.get(appel)
    if nom is None:
        return etat
    raison = precondition(appel, etat)
    budget = deps.budget_global_s - ecoule_s - deps.reserve_s
    tour = {"tour": len(etat.tours) + 1, "outil_appele": appel, "precondition": raison}
    if raison or budget <= SEUIL_BUDGET_S:  # GO2 refusée ou garde globale : revue humaine
        cause = "precondition" if raison else "duree"
        return replace(etat, cause=cause, tours=(*etat.tours, {**tour, "mode": "repli"}))
    rapport = await executer_agent(nom, etat, jeton, deps, min(SPECS[nom].delai_s, budget))
    try:
        neuf = fusionner(etat, rapport)
    except FusionRefusee:
        neuf = replace(etat, cause="fusion_refusee")
    neuf = replace(
        neuf,
        tours=(*etat.tours, {**tour, "mode": rapport.mode}),
        rapports=(*etat.rapports, _rapport(rapport, deps.trace_id())),
    )
    await _enregistrer_etat(neuf, "EN_COURS", jeton, deps)
    return neuf


def _rapport(rapport: Rapport, trace_id: str) -> dict[str, object]:
    return {
        "agent": rapport.agent,
        "rapport": vers_json(rapport.section),
        "mode": rapport.mode,
        "cause": rapport.cause,
        "version_prompt": rapport.version_prompt,
        "trace_id": trace_id,
    }


def statut_de(etat: EtatDossier) -> Literal["EN_ANALYSE", "REVUE_HUMAINE"]:
    proposee = prochaine_etape(etat)[0] == "proposer_au_gestionnaire"
    return "EN_ANALYSE" if proposee else "REVUE_HUMAINE"


def _fiche_provisoire(etat: EtatDossier, cause: str | None) -> Fiche:
    """R13 : brouillon de revue humaine ; le motif ne nomme jamais le détecteur."""
    r = etat.risque
    if cause and cause.startswith("garde_fou:entree:"):
        motif = "Contrôle d'entrée : revue humaine requise."
    else:
        motif = _MOTIFS.get(cause or "", "Revue humaine requise.")
    return Fiche(
        "REVUE_HUMAINE",
        "",
        r.score if r else 0,
        r.version_bareme if r else "inconnue",
        r.regle_ids if r else (),
        (motif,),
        (),
    )


async def proposer(etat: EtatDossier, jeton: str, deps: Dependances) -> EtatDossier:
    """Brouillon puis EN_ANALYSE (jamais ACCEPTE : K4), ou REVUE_HUMAINE avec fiche provisoire.

    Rend l'état sans ``observations`` : la pause humaine qui suit n'en a plus besoin.
    """
    statut = statut_de(etat)
    if statut == "REVUE_HUMAINE":
        cause = prochaine_etape(etat)[1]
        fiche = etat.fiche
        if fiche is None or fiche.decision != "REVUE_HUMAINE":  # la fiche suit le statut
            fiche = _fiche_provisoire(etat, cause)
        etat = replace(etat, fiche=fiche, prime=None)
    etat = replace(etat, observations=None)
    brouillon: dict[str, Any] = {
        "numero_contrat": etat.numero_contrat,
        "fiche": {**vers_json(etat.fiche), "score": float(etat.fiche.score)},  # type: ignore[union-attr]
    }
    if statut == "EN_ANALYSE" and etat.prime is not None:  # R1
        brouillon["prime"] = {
            "prime_ttc": float(etat.prime.prime_ttc_annuelle),
            "periodicite": "annuelle",
            "date_effet": (etat.dossier or {})["date_effet"],
        }
    await deps.outils.appeler(ORCHESTRATEUR, jeton, "enregistrer_brouillon", brouillon)
    await _enregistrer_etat(etat, statut, jeton, deps)
    await deps.outils.appeler(
        ORCHESTRATEUR,
        jeton,
        "update_statut_dossier",
        {"numero_contrat": etat.numero_contrat, "statut": statut},
    )
    return etat


async def enregistrer_revue(
    etat: EtatDossier, revue: Revue, jeton: str, deps: Dependances
) -> EtatDossier:
    """Le motif va dans la section ``validation`` (la table DECISION n'a pas de colonne motif)."""
    etat = replace(
        etat,
        validation={
            "decision": revue.decision,
            "validation": revue.validation,
            "motif": revue.motif,
        },
    )
    await _enregistrer_etat(etat, revue.decision, jeton, deps)
    await deps.outils.appeler(
        ORCHESTRATEUR,
        jeton,
        "update_statut_dossier",
        {
            "numero_contrat": etat.numero_contrat,
            "statut": revue.decision,
            "validation": revue.validation,
        },
    )
    return etat
