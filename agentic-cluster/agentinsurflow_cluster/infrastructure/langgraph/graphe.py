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
    DelaiDepasse,
    DossierDecide,
    EvaluationEnAttente,
    EvaluationEnCours,
    Revue,
)
from agentinsurflow_cluster.application.serialisation import etat_depuis_dict, etat_vers_dict
from agentinsurflow_cluster.domain.models import EtatDossier
from agentinsurflow_cluster.domain.ports import ErreurOutil

FINALISATION_S = 3.0  # budget 25 s + réserve 2 s + 3 s pour conclure : jamais plus de 30 s


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
    oid: str  # gestionnaire du dossier : posé au premier ``charger``, jamais écrasé par un autre
    tentative: int
    etat: dict[str, Any]
    debut: float
    statut: str | None
    revue: dict[str, Any] | None


@dataclass(frozen=True)
class Resultat:
    statut: str
    etat: EtatDossier


def construire_graphe(
    deps: Dependances, checkpointer: Any, pauses: set[tuple[str, str]] | None = None
) -> Any:
    """``pauses`` : demandes de pause (numéro, oid) lues entre deux agents (#129)."""
    pauses = set() if pauses is None else pauses

    async def charger(e: EtatGraphe, runtime: Runtime[Contexte]) -> EtatGraphe:
        debut = deps.horloge()
        etat = await evaluation.charger(
            e["numero"], runtime.context.jeton, deps, e.get("tentative", 1)
        )
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
        if evaluation.termine(etat_depuis_dict(e["etat"])):
            return "proposer"
        cle = (e["numero"], e["oid"])
        if cle in pauses:
            pauses.discard(cle)
            return "pause"
        return "pas"

    async def pause(e: EtatGraphe, runtime: Runtime[Contexte]) -> EtatGraphe:
        await evaluation.enregistrer_etat(
            etat_depuis_dict(e["etat"]), "EN_PAUSE", runtime.context.jeton, deps
        )
        return {"statut": "EN_PAUSE"}

    async def reprendre(e: EtatGraphe, runtime: Runtime[Contexte]) -> EtatGraphe:
        # nœud à part : LangGraph rejoue un nœud interrompu depuis son début (pas de 2e écriture)
        interrupt({"numero_contrat": e["numero"], "pause": True})
        runtime.context.memoire["observations"] = await evaluation.relire_observations(
            e["numero"], runtime.context.jeton, deps
        )
        return {"debut": deps.horloge(), "statut": None}  # budget neuf : la pause ne compte pas

    async def proposer(e: EtatGraphe, runtime: Runtime[Contexte]) -> EtatGraphe:
        pauses.discard((e["numero"], e["oid"]))  # une demande tardive est oubliée
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
    g.add_node("pause", pause)
    g.add_node("reprendre", reprendre)
    g.add_node("proposer", proposer)
    g.add_node("valider", valider)
    g.add_node("enregistrer", enregistrer)
    g.set_entry_point("charger")
    g.add_edge("charger", "pas")
    g.add_conditional_edges("pas", apres_pas, ["pas", "pause", "proposer"])
    g.add_edge("pause", "reprendre")
    g.add_edge("reprendre", "pas")
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
        self.reglages = deps.reglages  # lus par /health, avec les empreintes du démarrage
        self.versions_prompt = deps.versions_prompt
        self._budget_s = deps.budget_global_s + deps.reserve_s
        self._verrous: dict[str, asyncio.Lock] = {}
        # ponytail: en mémoire, une réplique (comme les verrous) ; perdue au redémarrage
        self._pauses: set[tuple[str, str]] = set()
        self._graphe = construire_graphe(deps, checkpointer, self._pauses)

    @staticmethod
    def _config(numero: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": numero}}

    def _verrou(self, numero: str) -> asyncio.Lock:
        return self._verrous.setdefault(numero, asyncio.Lock())

    async def _etat(self, numero: str) -> Any:
        return await self._graphe.aget_state(self._config(numero))

    @staticmethod
    def _attend(instantane: Any, noeud: str) -> bool:
        """Un ``interrupt()`` attend sur ``noeud`` (un échec antérieur ne compte pas)."""
        return any(t.interrupts for t in instantane.tasks if t.name == noeud)

    def _attend_revue(self, instantane: Any) -> bool:
        return self._attend(instantane, "valider")

    def _en_pause(self, instantane: Any) -> bool:
        return self._attend(instantane, "reprendre")

    @staticmethod
    def _a_rejouer(instantane: Any) -> bool:
        """La revue est posée mais ``enregistrer`` a échoué : elle ne doit pas être perdue."""
        return tuple(instantane.next) == ("enregistrer",) and bool(instantane.values.get("revue"))

    async def _resultat(self, numero: str) -> Resultat:
        valeurs = (await self._etat(numero)).values
        return Resultat(valeurs["statut"] or "EN_ANALYSE", etat_depuis_dict(valeurs["etat"]))

    async def _controler_proprietaire(self, numero: str, oid: str) -> Any:
        """BOLA : un dossier dont le point de reprise porte un autre ``oid`` n'existe pas (404)."""
        instantane = await self._etat(numero)
        # l'entrée {"oid": …} est écrite avant `charger` : un échec (404 d'un autre gestionnaire)
        # ne fait de personne le propriétaire ; seul un dossier effectivement chargé (`etat`) compte
        proprietaire = instantane.values.get("oid") if instantane.values.get("etat") else None
        if proprietaire is not None and proprietaire != oid:
            raise ErreurOutil("CONTRAT_INTROUVABLE")
        return instantane

    async def demander_pause(self, numero: str, oid: str) -> None:
        """Pause au prochain passage entre deux agents ; sans le verrou, l'évaluation tourne.

        Ignorée si plus aucun agent ne reste à appeler (revue attendue, dossier décidé, déjà en
        pause) : elle ne pèserait que sur une évaluation future.
        """
        instantane = await self._controler_proprietaire(numero, oid)
        if (
            self._attend_revue(instantane)
            or self._a_rejouer(instantane)
            or self._en_pause(instantane)
            or instantane.values.get("statut") in ("ACCEPTE", "REFUSE")
        ):
            return
        self._pauses.add((numero, oid))

    async def evaluer(self, numero: str, jeton: str, oid: str) -> Resultat:
        await self._controler_proprietaire(numero, oid)  # 404 avant 409 (BOLA)
        if self._verrou(numero).locked():  # double clic : ne pas attendre la première
            raise EvaluationEnCours(numero)
        async with self._verrou(numero):
            instantane = await self._controler_proprietaire(numero, oid)
            if self._attend_revue(instantane) or self._a_rejouer(instantane):
                raise EvaluationEnAttente(numero)
            if instantane.values.get("statut") in ("ACCEPTE", "REFUSE"):
                raise DossierDecide(numero)
            entree: Any
            if self._en_pause(instantane):  # reprise au point de reprise, même tentative
                entree = Command(resume=True)
            else:
                precedente = (instantane.values.get("etat") or {}).get("tentative", 0)
                entree = {"numero": numero, "oid": oid, "tentative": precedente + 1}
            try:
                async with asyncio.timeout(self._budget_s):
                    await self._graphe.ainvoke(
                        entree, self._config(numero), context=Contexte(jeton)
                    )
            except TimeoutError:
                await self._conclure_en_revue(numero, jeton)
            finally:  # demande non consommée (échec, arrivée pendant proposer) : jamais reportée
                self._pauses.discard((numero, oid))
            return await self._resultat(numero)

    async def _conclure_en_revue(self, numero: str, jeton: str) -> None:
        """Budget épuisé : revue humaine « duree » si un agent était en cours, sinon 503.

        Seul un point de reprise juste avant ``pas`` (dossier chargé, boucle des agents) permet de
        conclure ; ailleurs (lecture du contrat, écriture du brouillon) rien n'est cohérent à
        proposer, et l'évaluation peut être relancée telle quelle.
        """
        instantane = await self._etat(numero)
        if tuple(instantane.next) != ("pas",):
            raise DelaiDepasse(numero)
        etat = evaluation.delai_depasse(etat_depuis_dict(instantane.values["etat"]))
        config = self._config(numero)
        await self._graphe.aupdate_state(config, {"etat": etat_vers_dict(etat)}, as_node="pas")
        try:
            async with asyncio.timeout(FINALISATION_S):
                await self._graphe.ainvoke(None, config, context=Contexte(jeton))
        except TimeoutError as e:
            raise DelaiDepasse(numero) from e

    async def reviser(self, numero: str, revue: Revue, jeton: str, oid: str) -> Resultat:
        async with self._verrou(numero):
            instantane = await self._controler_proprietaire(numero, oid)
            if self._attend_revue(instantane):
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
