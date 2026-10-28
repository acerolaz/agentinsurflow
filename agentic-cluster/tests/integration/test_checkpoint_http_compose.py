"""TI — points de reprise contre le vrai underwriting-admin du compose, par la gateway.

Sauté si la gateway du compose ne répond pas, ou si aucun jeton d'application (rôle
``PointsDeReprise``, audience d'underwriting-admin) n'est posé dans ``JETON_POINTS_DE_REPRISE``.
Ne démarre ni n'arrête le compose.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from langgraph.checkpoint.base import empty_checkpoint

from agentinsurflow_cluster.infrastructure.langgraph.checkpoint_http import CheckpointerHttp

URL = os.environ.get("GATEWAY_URL", "http://localhost:8000")


@pytest.fixture
async def saver() -> AsyncIterator[CheckpointerHttp]:
    jeton = os.environ.get("JETON_POINTS_DE_REPRISE")
    if not jeton:
        pytest.skip("JETON_POINTS_DE_REPRISE absent : aucun jeton disponible")
    try:
        httpx.get(f"{URL}/health", timeout=2)
    except httpx.HTTPError:
        pytest.skip(f"gateway du compose injoignable ({URL})")
    async with httpx.AsyncClient(base_url=URL, timeout=30) as client:
        yield CheckpointerHttp(client, lambda: jeton)


async def test_aller_retour_complet_par_la_gateway(saver: CheckpointerHttp) -> None:
    fil = f"AIF-TI-{uuid.uuid4().hex[:8]}"
    cp = empty_checkpoint()
    cp["channel_values"] = {"etat": {"v": 1}}
    suivant = await saver.aput(
        {"configurable": {"thread_id": fil, "checkpoint_ns": ""}}, cp, {"step": 0}, {"etat": 1}
    )
    await saver.aput_writes(suivant, [("canal", "valeur")], "tache", "")
    try:
        tuple_ = await saver.aget_tuple({"configurable": {"thread_id": fil}})
        assert tuple_ is not None
        assert tuple_.checkpoint["channel_values"] == {"etat": {"v": 1}}
        assert tuple_.pending_writes == [("tache", "canal", "valeur")]
    finally:
        await saver.adelete_thread(fil)
    assert await saver.aget_tuple({"configurable": {"thread_id": fil}}) is None
