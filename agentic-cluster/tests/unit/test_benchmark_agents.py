"""TU — ``benchmark_agents.py`` : une mesure reflète ce que rend l'adapter, sans planter."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import httpx
from openai import OpenAI

from agentinsurflow_cluster.domain.ports import CAUSE_BUDGET

_RACINE = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("benchmark_agents", _RACINE / "benchmark_agents.py")
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
sys.modules["benchmark_agents"] = _module
_spec.loader.exec_module(_module)
mesurer = _module.mesurer
preflight = _module.preflight


class Faux:
    def __init__(self, sortie: dict[str, Any] | None) -> None:
        self.sortie = sortie

    async def rediger(
        self, agent: str, vue: dict[str, Any], budget_s: float, jeton: str = ""
    ) -> dict[str, Any] | None:
        return self.sortie


class FauxQuiLeve:
    def __init__(self, erreur: Exception) -> None:
        self.erreur = erreur

    async def rediger(
        self, agent: str, vue: dict[str, Any], budget_s: float, jeton: str = ""
    ) -> dict[str, Any] | None:
        raise self.erreur


def _mesure(redaction: Any) -> dict[str, Any]:
    return asyncio.run(mesurer(redaction, "m", "pieces", "A", 1, {}))


def test_reponse_valide_donne_ok_et_tokens() -> None:
    m = _mesure(Faux({"note": "n", "usage": {"entree": 10, "sortie": 5}}))
    assert (m["statut"], m["cause"], m["tokens_entree"], m["tokens_sortie"]) == ("ok", None, 10, 5)


def test_none_est_un_echec_llm_ko() -> None:
    m = _mesure(Faux(None))
    assert (m["statut"], m["cause"]) == ("echec", "llm_ko")


def test_erreur_budget_est_un_echec_nomme() -> None:
    m = _mesure(Faux({"erreur": CAUSE_BUDGET, "usage": {"entree": 3, "sortie": 400}}))
    assert (m["statut"], m["cause"], m["tokens_sortie"]) == ("echec", CAUSE_BUDGET, 400)


def test_exception_du_modele_ne_plante_pas_la_campagne() -> None:
    m = _mesure(FauxQuiLeve(TimeoutError()))
    assert (m["statut"], m["cause"]) == ("echec", "TimeoutError")


def test_sources_du_redacteur_comptees() -> None:
    m = asyncio.run(mesurer(Faux({"sources": [{}, {}], "usage": {}}), "m", "redacteur", "A", 1, {}))
    assert m["nb_sources"] == 2


def test_redacteur_sans_source_est_un_echec() -> None:
    m = asyncio.run(mesurer(Faux({"sources": [], "usage": {}}), "m", "redacteur", "A", 1, {}))
    assert (m["statut"], m["cause"]) == ("echec", "sans_source")


def test_preflight_garde_le_429() -> None:
    transport = httpx.MockTransport(
        lambda _r: httpx.Response(429, json={"error": {"message": "limite"}})
    )
    client = OpenAI(
        base_url="http://test/v1/",
        api_key="x",
        max_retries=0,
        http_client=httpx.Client(transport=transport),
    )
    assert preflight(client, "m") == {"modele": "m", "http": 429, "erreur": "RateLimitError"}


def test_preflight_reussi() -> None:
    corps = {
        "id": "1",
        "object": "chat.completion",
        "created": 1,
        "model": "m",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": "ok"},
            }
        ],
    }
    transport = httpx.MockTransport(lambda _r: httpx.Response(200, json=corps))
    client = OpenAI(
        base_url="http://test/v1/",
        api_key="x",
        max_retries=0,
        http_client=httpx.Client(transport=transport),
    )
    assert preflight(client, "m") == {"modele": "m", "http": 200, "erreur": None}


def test_vues_fictives_completes_et_sans_donnee_personnelle() -> None:
    vues = json.loads((_RACINE.parent / "eval/benchmark/vues.json").read_text(encoding="utf-8"))
    assert set(vues) == {"acceptable", "limite", "refus"}
    cles = {
        "pieces": {"statut", "manquantes", "pieces_exigees"},
        "analyste": {"score", "classe", "regle_ids", "version_bareme"},
        "redacteur": {"classe", "score", "regle_ids", "version_bareme", "formule", "observations"},
        "actuaire": {"prime_ttc_annuelle", "prime_mensuelle", "version_formule"},
    }
    for dossier in vues.values():
        assert {agent: set(vue) for agent, vue in dossier.items()} == cles
    assert "@" not in json.dumps(vues)
