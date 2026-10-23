"""Graphe LangGraph : ``charger → pas (boucle) → proposer → valider [interrupt()] → enregistrer``.

Le graphe ne chaîne que les fonctions de ``application.evaluation`` et porte la pause humaine :
``thread_id = numero_contrat``. L'état du graphe est JSON-safe (``etat_vers_dict``) : un point de
reprise de LangGraph transforme les tuples en listes. Le jeton du gestionnaire passe par le
*contexte* d'exécution, jamais par l'état : il n'est donc écrit dans aucun point de reprise.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field, replace
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command, interrupt

from agentinsurflow_cluster.application import evaluation
from agentinsurflow_cluster.application.agents import Dependances
from agentinsurflow_cluster.application.evaluation import (
    AucuneRevueEnAttente,
    DossierDecide,
    EvaluationEnAttente,
    Revue,
)
from agentinsurflow_cluster.application.serialisation import etat_depuis_dict, etat_vers_dict
from agentinsurflow_cluster.domain.models import EtatDossier


@dataclass(frozen=True)
class Contexte:
    """Contexte d'exécution, jamais écrit dans un point de reprise (R16, D26).

    ``memoire`` porte le texte des observations le temps de l'exécution : il ne quitte jamais
    le processus, donc aucun checkpoint ne le contient.
    """

    jeton: str
    memoire: dict[str, str | None] = field(default_factory=dict)


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
        runtime.context.memoire["observations"] = etat.observations
        etat = replace(etat, observations=None)
        return {"etat": etat_vers_dict(etat), "debut": debut, "statut": None, "revue": None}

    async def pas(e: EtatGraphe, runtime: Runtime[Contexte]) -> EtatGraphe:
        courant = replace(
            etat_depuis_dict(e["etat"]), observations=runtime.context.memoire.get("observations")
        )
        etat = await evaluation.pas(
            courant, runtime.context.jeton, deps, deps.horloge() - e["debut"]
        )
        return {"etat": etat_vers_dict(replace(etat, observations=None))}

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
    """Ce que les routes appellent : évaluer, puis reprendre sur la revue du gestionnaire.

    Un verrou par dossier sérialise ``evaluer`` et ``reviser`` : valable pour une seule réplique
    (``maxReplicas: 1``) ; plusieurs répliques demanderaient un verrou en base (advisory lock).
    """

    def __init__(self, deps: Dependances, checkpointer: Any) -> None:
        self._graphe = construire_graphe(deps, checkpointer)
        self._verrous: dict[str, asyncio.Lock] = {}

    @staticmethod
    def _config(numero: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": numero}}

    def _verrou(self, numero: str) -> asyncio.Lock:
        return self._verrous.setdefault(numero, asyncio.Lock())

    async def _etat(self, numero: str) -> Any:
        return await self._graphe.aget_state(self._config(numero))

    @staticmethod
    def _en_pause(instantane: Any) -> bool:
        """Un ``interrupt()`` attend (un échec antérieur ne compte pas)."""
        return any(t.interrupts for t in instantane.tasks)

    @staticmethod
    def _a_rejouer(instantane: Any) -> bool:
        """La revue est posée mais ``enregistrer`` a échoué : elle ne doit pas être perdue."""
        return tuple(instantane.next) == ("enregistrer",) and bool(instantane.values.get("revue"))

    async def _resultat(self, numero: str) -> Resultat:
        valeurs = (await self._etat(numero)).values
        return Resultat(valeurs["statut"] or "EN_ANALYSE", etat_depuis_dict(valeurs["etat"]))

    async def evaluer(self, numero: str, jeton: str) -> Resultat:
        async with self._verrou(numero):
            instantane = await self._etat(numero)
            if self._en_pause(instantane) or self._a_rejouer(instantane):
                raise EvaluationEnAttente(numero)
            if instantane.values.get("statut") in ("ACCEPTE", "REFUSE"):
                raise DossierDecide(numero)
            await self._graphe.ainvoke(
                {"numero": numero}, self._config(numero), context=Contexte(jeton)
            )
            return await self._resultat(numero)

    async def reviser(self, numero: str, revue: Revue, jeton: str) -> Resultat:
        async with self._verrou(numero):
            instantane = await self._etat(numero)
            if self._en_pause(instantane):
                entree: Any = Command(resume=asdict(revue))
            elif self._a_rejouer(instantane):  # la décision la plus récente l'emporte
                await self._graphe.aupdate_state(
                    self._config(numero), {"revue": asdict(revue)}, as_node="valider"
                )
                entree = None
            else:
                raise AucuneRevueEnAttente(numero)
            await self._graphe.ainvoke(entree, self._config(numero), context=Contexte(jeton))
            return await self._resultat(numero)
