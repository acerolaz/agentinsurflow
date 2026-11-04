#!/usr/bin/env python3
"""Benchmark C7, usage agents : l'adapter réel, les vrais prompts, par la gateway locale.

Seul ``modele`` change d'un candidat à l'autre : les réglages de ``agents.toml`` ne sont pas
adaptés, un refus du modèle est un résultat. À lancer après ``make up`` (procédure :
``eval/preuves/benchmark-2026-11-03/README.md``). Jetons : celui de ``rag`` (rôle ``LLM``) pour
``/api/llm``, ``EVALS_JETON`` (rôle ``Gestionnaire``) pour ``/api/extraits``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import openai
from azure.identity import ClientSecretCredential, get_bearer_token_provider
from langchain_openai import ChatOpenAI
from openai import OpenAI

from agentinsurflow_cluster.domain.models import NomAgent
from agentinsurflow_cluster.domain.ports import ErreurOutil, RedactionPort
from agentinsurflow_cluster.infrastructure.llm.fabrique import RedactionLangChain
from agentinsurflow_cluster.infrastructure.llm.reglages import charger_reglages

BUDGET_S = 30.0  # commun : la latence réelle est mesurée même au-delà de ``delai_s``
PAUSE_S = 3.0  # limite de la gateway : 30 appels LLM par minute
AGENTS: tuple[NomAgent, ...] = ("pieces", "analyste", "redacteur", "actuaire")
VUES = Path(__file__).resolve().parents[1] / "eval/benchmark/vues.json"
_ERREURS_CAMPAGNE = (TimeoutError, OSError, ValueError, RuntimeError)


async def mesurer(
    redaction: RedactionPort,
    modele: str,
    agent: NomAgent,
    dossier: str,
    essai: int,
    vue: dict[str, Any],
    budget_s: float = BUDGET_S,
) -> dict[str, Any]:
    """Une mesure : ``statut`` vaut ``ok`` ou ``echec``, avec la cause rendue par l'adapter."""
    debut = time.perf_counter()
    cause: str | None
    try:
        sortie = await redaction.rediger(agent, vue, budget_s)
    except _ERREURS_CAMPAGNE as e:  # un candidat qui plante ne doit pas perdre la campagne
        sortie, cause = None, type(e).__name__
    else:
        cause = "llm_ko" if sortie is None else (sortie.get("erreur") or None)
    latence = time.perf_counter() - debut
    usage = (sortie or {}).get("usage") or {}
    nb_sources = len((sortie or {}).get("sources", []))
    if cause is None and agent == "redacteur" and nb_sources == 0:
        cause = "sans_source"  # sans citation, l'appel d'outil n'a rien prouvé
    return {
        "modele": modele,
        "agent": agent,
        "dossier": dossier,
        "essai": essai,
        "latence_s": round(latence, 3),
        "statut": "echec" if cause else "ok",
        "cause": cause,
        "tokens_entree": usage.get("entree", 0),
        "tokens_sortie": usage.get("sortie", 0),
        "nb_sources": nb_sources,
    }


def preflight(client: OpenAI, modele: str) -> dict[str, Any]:
    """Un appel minimal : ``rediger`` ne rend que ``None``, ceci nomme le refus réel du modèle."""
    try:
        client.chat.completions.create(
            model=modele,
            messages=[{"role": "user", "content": "Réponds : ok."}],
            temperature=0.0,  # comme les agents : révèle un modèle qui refuse ce réglage
            max_completion_tokens=16,
        )
    except openai.APIStatusError as e:
        print(f"preflight {modele} : {e.status_code} {e.message[:300]}", file=sys.stderr)
        return {"modele": modele, "http": e.status_code, "erreur": type(e).__name__}
    except openai.APIConnectionError as e:
        return {"modele": modele, "http": None, "erreur": type(e).__name__}
    return {"modele": modele, "http": 200, "erreur": None}


class OutilsLocaux:
    """``search_rag`` du Rédacteur, servi par ``GET /api/extraits`` de la gateway locale."""

    def __init__(self, gateway: str, jeton: str) -> None:
        self._url, self._entetes = f"{gateway}/api/extraits", {"Authorization": f"Bearer {jeton}"}

    async def appeler(
        self, agent: str, jeton: str, outil: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        parametres = {k: v for k, v in arguments.items() if v is not None}
        async with httpx.AsyncClient(timeout=BUDGET_S) as http:
            try:
                reponse = await http.get(self._url, params=parametres, headers=self._entetes)
            except httpx.HTTPError as e:
                raise ErreurOutil("MCP_INDISPONIBLE", type(e).__name__) from e
        if reponse.status_code != 200:
            raise ErreurOutil("MCP_INDISPONIBLE", f"HTTP {reponse.status_code}")
        return reponse.json()  # type: ignore[no-any-return]


def _ecrire(sortie: Path, campagne: dict[str, Any]) -> None:
    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.write_text(json.dumps(campagne, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


async def campagne(modeles: list[str], essais: int, sortie: Path) -> dict[str, Any]:
    gateway = os.environ.get("GATEWAY_LOCALE", "http://localhost:8000").rstrip("/")
    jeton_llm = get_bearer_token_provider(
        ClientSecretCredential(
            os.environ["AZURE_TENANT_ID"],
            os.environ["RAG_API_CLIENT_ID"],
            os.environ["RAG_CLIENT_SECRET"],
        ),
        f"{os.environ['LLM_AUDIENCE']}/.default",
    )
    base = f"{gateway}/api/llm/v1/"
    outils = OutilsLocaux(gateway, os.environ["EVALS_JETON"])
    vues = json.loads(VUES.read_text(encoding="utf-8"))
    reglages = charger_reglages(BUDGET_S * 4)
    resultat: dict[str, Any] = {"preflight": [], "mesures": []}
    for modele in modeles:
        client = OpenAI(base_url=base, api_key=jeton_llm, timeout=BUDGET_S, max_retries=0)
        resultat["preflight"].append(preflight(client, modele))
        par_agent = {a: replace(r, modele=modele) for a, r in reglages.items()}

        def chat(agent: NomAgent, reglages_modele: Any = par_agent) -> ChatOpenAI:
            reglage = reglages_modele[agent]
            return ChatOpenAI(
                base_url=base,
                api_key=jeton_llm,
                model=reglage.modele,
                temperature=reglage.temperature,
                max_completion_tokens=reglage.max_tokens,
                timeout=BUDGET_S,
                max_retries=0,
            )

        redaction = RedactionLangChain(chat, outils, par_agent)
        for dossier, par_vue in vues.items():
            for agent in AGENTS:
                for essai in range(1, essais + 1):
                    mesure = await mesurer(redaction, modele, agent, dossier, essai, par_vue[agent])
                    resultat["mesures"].append(mesure)
                    _ecrire(sortie, resultat)  # une panne ne perd pas les mesures déjà faites
                    print(f"{modele} {agent} {dossier} {essai} : {mesure['statut']}", flush=True)
                    await asyncio.sleep(PAUSE_S)
    return resultat


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modeles", nargs="+", required=True)
    parser.add_argument("--essais", type=int, default=3)
    parser.add_argument("--sortie", type=Path, required=True)
    args = parser.parse_args(argv)
    asyncio.run(campagne(args.modeles, args.essais, args.sortie))
    print(f"✔ {args.sortie}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
