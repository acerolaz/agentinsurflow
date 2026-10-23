"""Graphe LangGraph : ``charger → pas (boucle) → proposer → valider [interrupt()] → enregistrer``.

Le graphe ne chaîne que les fonctions de ``application.evaluation`` et porte la pause humaine :
``thread_id = numero_contrat``. L'état du graphe est JSON-safe (``etat_vers_dict``) : un point de
reprise de LangGraph transforme les tuples en listes. Le jeton du gestionnaire passe par le
*contexte* d'exécution, jamais par l'état : il n'est donc écrit dans aucun point de reprise.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command, interrupt

from agentinsurflow_cluster.application import evaluation
from agentinsurflow_cluster.application.agents import Dependances
from agentinsurflow_cluster.application.evaluation import (
    AucuneRevueEnAttente,
    EvaluationEnAttente,
    Revue,
)
from agentinsurflow_cluster.application.serialisation import etat_depuis_dict, etat_vers_dict
from agentinsurflow_cluster.domain.models import EtatDossier


@dataclass(frozen=True)
class Contexte:
    jeton: str


class EtatGraphe(TypedDict, total=False):
    numero: str
    etat: dict[str, Any]
    debut: float
    statut: str | None
    revue: dict[str, Any] | None


@dataclass(frozen=True)
class Resultat:
    statut: str
    etat: EtatDossier


def construire_graphe(deps: Dependances, checkpointer: Any) -> Any:
    async def charger(e: EtatGraphe, runtime: Runtime[Contexte]) -> EtatGraphe:
        debut = deps.horloge()
        etat = await evaluation.charger(e["numero"], runtime.context.jeton, deps)
        return {"etat": etat_vers_dict(etat), "debut": debut, "statut": None, "revue": None}

    async def pas(e: EtatGraphe, runtime: Runtime[Contexte]) -> EtatGraphe:
        etat = await evaluation.pas(
            etat_depuis_dict(e["etat"]), runtime.context.jeton, deps, deps.horloge() - e["debut"]
        )
        return {"etat": etat_vers_dict(etat)}

    def apres_pas(e: EtatGraphe) -> str:
        return "proposer" if evaluation.termine(etat_depuis_dict(e["etat"])) else "pas"

    async def proposer(e: EtatGraphe, runtime: Runtime[Contexte]) -> EtatGraphe:
        etat = await evaluation.proposer(etat_depuis_dict(e["etat"]), runtime.context.jeton, deps)
        return {"etat": etat_vers_dict(etat), "statut": evaluation.statut_de(etat)}

    def apres_proposer(e: EtatGraphe) -> str:
        return "valider" if e["statut"] == "EN_ANALYSE" else END

    def valider(e: EtatGraphe) -> EtatGraphe:
        # la charge de l'interruption ne porte rien de personnel : le numéro seulement
        return {"revue": interrupt({"numero_contrat": e["numero"]})}

    async def enregistrer(e: EtatGraphe, runtime: Runtime[Contexte]) -> EtatGraphe:
        revue = Revue(**(e["revue"] or {}))
        etat = await evaluation.enregistrer_revue(
            etat_depuis_dict(e["etat"]), revue, runtime.context.jeton, deps
        )
        return {"etat": etat_vers_dict(etat), "statut": revue.decision}

    g: Any = StateGraph(EtatGraphe, context_schema=Contexte)  # typage des nœuds : trop strict
    g.add_node("charger", charger)
    g.add_node("pas", pas)
    g.add_node("proposer", proposer)
    g.add_node("valider", valider)
    g.add_node("enregistrer", enregistrer)
    g.set_entry_point("charger")
    g.add_edge("charger", "pas")
    g.add_conditional_edges("pas", apres_pas, ["pas", "proposer"])
    g.add_conditional_edges("proposer", apres_proposer, ["valider", END])
    g.add_edge("valider", "enregistrer")
    g.add_edge("enregistrer", END)
    return g.compile(checkpointer=checkpointer)


class ServiceEvaluation:
    """Ce que les routes appellent : évaluer, puis reprendre sur la revue du gestionnaire."""

    def __init__(self, deps: Dependances, checkpointer: Any) -> None:
        self._graphe = construire_graphe(deps, checkpointer)

    @staticmethod
    def _config(numero: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": numero}}

    async def _en_attente(self, numero: str) -> bool:
        """Vrai si un ``interrupt()`` attend (un échec antérieur ne compte pas)."""
        instantane = await self._graphe.aget_state(self._config(numero))
        return any(t.interrupts for t in instantane.tasks)

    async def _resultat(self, numero: str) -> Resultat:
        valeurs = (await self._graphe.aget_state(self._config(numero))).values
        return Resultat(valeurs["statut"] or "EN_ANALYSE", etat_depuis_dict(valeurs["etat"]))

    async def evaluer(self, numero: str, jeton: str) -> Resultat:
        if await self._en_attente(numero):
            raise EvaluationEnAttente(numero)
        await self._graphe.ainvoke(
            {"numero": numero}, self._config(numero), context=Contexte(jeton)
        )
        return await self._resultat(numero)

    async def reviser(self, numero: str, revue: Revue, jeton: str) -> Resultat:
        if not await self._en_attente(numero):
            raise AucuneRevueEnAttente(numero)
        commande: Command[Any] = Command(
            resume={
                "decision": revue.decision,
                "validation": revue.validation,
                "motif": revue.motif,
            }
        )
        await self._graphe.ainvoke(commande, self._config(numero), context=Contexte(jeton))
        return await self._resultat(numero)
