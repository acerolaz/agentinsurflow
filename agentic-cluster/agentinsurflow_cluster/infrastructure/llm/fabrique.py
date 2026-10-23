"""Adapter LangChain de ``RedactionPort`` : un ``create_agent`` par appel et par agent.

Le LLM ne rédige que le champ de son agent (``response_format``) ; le Rédacteur seul reçoit
l'outil ``search_rag`` (≤ 5 appels), dont le code copie les résultats dans ``sources``.
Tout échec (modèle absent, délai, e-mail en sortie, format invalide) rend ``None`` : repli.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

import httpx
import openai
from langchain.agents import create_agent
from langchain.agents.middleware import (
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
from ...domain.ports import ErreurOutil, OutilsPort
from ...domain.specs import SPECS

PROMPTS = Path(__file__).parent / "prompts"
MAX_RECHERCHES = 5
CAUSE_PII = "garde_fou:pii"


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


def version_prompt(nom: NomAgent) -> str:
    return hashlib.sha256((PROMPTS / f"{nom}.md").read_bytes()).hexdigest()[:12]


def _source(extrait: dict[str, Any]) -> dict[str, Any]:
    """Extrait RAG aplati : ``doc_id`` et ``collection`` d'abord, texte inclus."""
    return {**extrait.get("citation", {}), "texte": extrait.get("texte", "")}


def _balisee(sources: list[dict[str, Any]]) -> str:
    corps = "\n".join(f"[{s.get('doc_id')}] {s['texte']}" for s in sources) or "Aucun extrait."
    return f"{DEBUT_BALISE}{corps.replace(FIN_BALISE, '')}{FIN_BALISE}"


class RedactionLangChain:
    """Adapter de ``RedactionPort`` ; `modele(nom)` rend ``None`` quand le LLM est désactivé."""

    def __init__(self, modele: Callable[[NomAgent], BaseChatModel | None], outils: OutilsPort):
        self._modele, self._outils = modele, outils

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
        middleware: list[Any] = [ModelCallLimitMiddleware(run_limit=SPECS[agent].tours_max)]
        if outils:
            middleware.append(ToolCallLimitMiddleware(run_limit=MAX_RECHERCHES))
        middleware.append(PIIMiddleware("email", strategy="block", apply_to_output=True))
        lc = create_agent(
            model=modele,
            tools=outils,
            system_prompt=(PROMPTS / f"{agent}.md").read_text(encoding="utf-8"),
            response_format=FORMATS[agent],
            middleware=middleware,
        )
        entree = {"messages": [{"role": "user", "content": json.dumps(vue, ensure_ascii=False)}]}
        try:
            async with asyncio.timeout(budget_s):
                resultat = await lc.ainvoke(entree)  # type: ignore[call-overload]
        except PIIDetectionError:  # K5 : un garde-fou, pas une panne du LLM
            return {"erreur": CAUSE_PII}
        except _ERREURS_LLM:
            return None
        champs = resultat.get("structured_response")
        if champs is None:
            return None
        if agent != "redacteur":
            return champs.model_dump()  # type: ignore[no-any-return]
        if erreurs and not sources:  # rien de citable : l'application en tire la cause
            return {"erreur": erreurs[-1]}
        return {**champs.model_dump(), "sources": sources}
