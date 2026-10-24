"""Adapter LangChain de ``RedactionPort`` : un ``create_agent`` par appel et par agent.

Le LLM ne rédige que le champ de son agent (``response_format``) ; le Rédacteur seul reçoit
l'outil ``search_rag`` (≤ 5 appels), dont le code copie les résultats dans ``sources``.
Tout échec (modèle absent, délai, e-mail en sortie, format invalide) rend ``None`` : repli.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Literal

import httpx
import openai
from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelCallLimitMiddleware,
    PIIDetectionError,
    PIIMiddleware,
    ToolCallLimitMiddleware,
)
from langchain.agents.structured_output import StructuredOutputError
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, ValidationError

from ...domain.balises import DEBUT_BALISE, FIN_BALISE
from ...domain.models import NomAgent
from ...domain.ports import CAUSE_BUDGET, CAUSE_PII, ErreurOutil, OutilsPort
from ...domain.reglages import ReglageAgent
from ...domain.specs import SPECS

PROMPTS = Path(__file__).parent / "prompts"
MAX_RECHERCHES = 5


class _Tronque(Exception):
    """Une réponse du modèle a été coupée par ``max_tokens`` (``finish_reason == "length"``)."""


class _DetecteTroncature(AgentMiddleware):
    """Voit la réponse brute, avant l'analyse du format : une sortie coupée n'est pas analysable.

    Une instance par appel de ``rediger`` : ``usage`` somme les tokens de tous ses appels.
    """

    def __init__(self) -> None:
        super().__init__()
        self.usage = {"entree": 0, "sortie": 0}

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        reponse = await handler(request)
        for cle, v in _usage(reponse.result).items():
            self.usage[cle] += v
        if any(m.response_metadata.get("finish_reason") == "length" for m in reponse.result):
            raise _Tronque
        return reponse


def _usage(messages: list[Any]) -> dict[str, int]:
    metas = [m.usage_metadata or {} for m in messages if m.type == "ai"]
    return {
        "entree": sum(u.get("input_tokens", 0) for u in metas),
        "sortie": sum(u.get("output_tokens", 0) for u in metas),
    }


class Note(BaseModel):
    note: str


class ExplicationPrime(BaseModel):
    explication: str


class FicheRedigee(BaseModel):
    decision: Literal["ACCEPTE", "REFUSE", "REVUE_HUMAINE"]
    contrat_type: str
    motifs: list[str]
    citations: list[str]


FORMATS: dict[NomAgent, type[BaseModel]] = {
    "pieces": Note,
    "analyste": Note,
    "redacteur": FicheRedigee,
    "actuaire": ExplicationPrime,
}
_ERREURS_LLM = (
    TimeoutError,
    StructuredOutputError,
    ValidationError,
    openai.OpenAIError,
    httpx.HTTPError,
)


def version_prompt(fichier: str) -> str:
    return hashlib.sha256((PROMPTS / fichier).read_bytes()).hexdigest()[:12]


def _source(extrait: dict[str, Any]) -> dict[str, Any]:
    """Extrait RAG aplati : ``doc_id`` et ``collection`` d'abord, texte inclus."""
    return {**extrait.get("citation", {}), "texte": extrait.get("texte", "")}


def _balisee(sources: list[dict[str, Any]]) -> str:
    corps = "\n".join(f"[{s.get('doc_id')}] {s['texte']}" for s in sources) or "Aucun extrait."
    return f"{DEBUT_BALISE}{corps.replace(FIN_BALISE, '')}{FIN_BALISE}"


class RedactionLangChain:
    """Adapter de ``RedactionPort`` ; `modele(nom)` rend ``None`` quand le LLM est désactivé."""

    def __init__(
        self,
        modele: Callable[[NomAgent], BaseChatModel | None],
        outils: OutilsPort,
        reglages: Mapping[NomAgent, ReglageAgent],
    ):
        self._modele, self._outils, self._reglages = modele, outils, reglages

    def _search_rag(
        self, jeton: str, sources: list[dict[str, Any]], erreurs: list[str]
    ) -> BaseTool:
        async def search_rag(question: str, top_k: int | None = None) -> str:
            """Cherche dans le corpus d'assurance les extraits cités qui répondent à la question."""
            try:
                retour = await self._outils.appeler(
                    "redacteur", jeton, "search_rag", {"question": question, "top_k": top_k}
                )
            except ErreurOutil as e:
                erreurs.append(e.code)
                return f"Erreur : {e.code}. Aucun extrait."
            nouvelles = [_source(x) for x in retour.get("resultats", [])]
            sources.extend(nouvelles)
            return _balisee(nouvelles)

        return StructuredTool.from_function(coroutine=search_rag, name="search_rag")

    async def rediger(
        self, agent: NomAgent, vue: dict[str, Any], budget_s: float, jeton: str = ""
    ) -> dict[str, Any] | None:
        modele = self._modele(agent)
        if modele is None:
            return None
        sources: list[dict[str, Any]] = []
        erreurs: list[str] = []
        outils = [self._search_rag(jeton, sources, erreurs)] if agent == "redacteur" else []
        troncature = _DetecteTroncature()
        middleware: list[Any] = [
            ModelCallLimitMiddleware(run_limit=SPECS[agent].tours_max),
            troncature,
        ]
        if outils:
            middleware.append(ToolCallLimitMiddleware(run_limit=MAX_RECHERCHES))
        middleware.append(PIIMiddleware("email", strategy="block", apply_to_output=True))
        lc = create_agent(
            model=modele,
            tools=outils,
            system_prompt=(PROMPTS / self._reglages[agent].prompt).read_text(encoding="utf-8"),
            response_format=FORMATS[agent],
            middleware=middleware,
        )
        entree = {"messages": [{"role": "user", "content": json.dumps(vue, ensure_ascii=False)}]}
        try:
            async with asyncio.timeout(budget_s):
                resultat = await lc.ainvoke(entree)  # type: ignore[call-overload]
        except PIIDetectionError:  # K5 : un garde-fou, pas une panne du LLM
            return {"erreur": CAUSE_PII}
        except (_Tronque, openai.LengthFinishReasonError) as e:  # avant _ERREURS_LLM (sous-classe)
            if isinstance(e, openai.LengthFinishReasonError) and e.completion.usage:
                troncature.usage["entree"] += e.completion.usage.prompt_tokens
                troncature.usage["sortie"] += e.completion.usage.completion_tokens
            return {"erreur": CAUSE_BUDGET, "usage": troncature.usage}
        except _ERREURS_LLM:
            return None
        champs = resultat.get("structured_response")
        if champs is None:
            return None
        usage = _usage(resultat.get("messages", []))
        if agent != "redacteur":
            return {**champs.model_dump(), "usage": usage}
        if erreurs and not sources:  # rien de citable : l'application en tire la cause
            return {"erreur": erreurs[-1]}
        return {**champs.model_dump(), "sources": sources, "usage": usage}
