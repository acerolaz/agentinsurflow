"""Points de reprise LangGraph stockés par la gateway dans underwriting-admin (D105).

Même sémantique qu'``AsyncPostgresSaver`` : ``aput`` renvoie la config avec le ``checkpoint_id``,
``aput_writes`` indexe les canaux spéciaux par ``WRITES_IDX_MAP`` (sinon par position), ``alist``
filtre les métadonnées côté client. Les ``channel_values`` restent dans le checkpoint sérialisé
(``serde.dumps_typed``) : underwriting-admin stocke des octets opaques, sans table de blobs.

Aucun repli : une erreur de jeton ou HTTP remonte, jamais de point vide ; le corps n'est pas tracé.
"""

from __future__ import annotations

import asyncio
import base64
from collections.abc import AsyncIterator, Callable, Sequence
from typing import Any
from urllib.parse import quote

import httpx
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    WRITES_IDX_MAP,
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    get_serializable_checkpoint_metadata,
    writes_sort_key,
)

RACINE = "/api/points-de-reprise/"


def _b64(octets: bytes) -> str:
    return base64.b64encode(octets).decode("ascii")


class CheckpointerHttp(BaseCheckpointSaver[str]):
    """``jeton`` est appelé (dans un thread) avant chaque requête ; le cache est celui du SDK."""

    def __init__(self, client: httpx.AsyncClient, jeton: Callable[[], str]) -> None:
        super().__init__()
        self.client = client
        self.jeton = jeton

    async def _appeler(self, methode: str, chemin: str, **kw: Any) -> httpx.Response:
        jeton = await asyncio.to_thread(self.jeton)
        reponse = await self.client.request(
            methode,
            RACINE + chemin,
            headers={"Authorization": f"Bearer {jeton}"},
            **kw,
        )
        if reponse.status_code != 404:  # seul 404 a un sens (point absent) ; le reste remonte
            reponse.raise_for_status()
        return reponse

    def _tuple(self, fil: str, p: dict[str, Any]) -> CheckpointTuple:
        checkpoint: Checkpoint = self.serde.loads_typed(
            (p["type"], base64.b64decode(p["checkpoint"]))
        )
        metadata = self.serde.loads_typed((p["type_metadata"], base64.b64decode(p["metadata"])))
        ecritures = sorted(
            p.get("ecritures", []),
            key=lambda e: writes_sort_key(e["task_path"], e["task_id"], e["idx"]),
        )
        return CheckpointTuple(
            config={
                "configurable": {
                    "thread_id": fil,
                    "checkpoint_ns": p["ns"],
                    "checkpoint_id": p["checkpoint_id"],
                }
            },
            checkpoint=checkpoint,
            metadata=metadata,
            parent_config=(
                {
                    "configurable": {
                        "thread_id": fil,
                        "checkpoint_ns": p["ns"],
                        "checkpoint_id": p["parent_id"],
                    }
                }
                if p.get("parent_id")
                else None
            ),
            pending_writes=[
                (
                    e["task_id"],
                    e["canal"],
                    self.serde.loads_typed((e["type"], base64.b64decode(e["valeur"]))),
                )
                for e in ecritures
            ],
        )

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        c = config["configurable"]
        fil = c["thread_id"]
        params = {"ns": c.get("checkpoint_ns", "")}
        if c.get("checkpoint_id"):
            params["id"] = c["checkpoint_id"]
        reponse = await self._appeler("GET", quote(fil, safe=""), params=params)
        return None if reponse.status_code == 404 else self._tuple(fil, reponse.json())

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        if config is None:
            raise NotImplementedError("alist sans fil (thread_id) n'est pas pris en charge")
        c = config["configurable"]
        fil = c["thread_id"]
        params: dict[str, Any] = {}
        if c.get("checkpoint_ns") is not None:
            params["ns"] = c["checkpoint_ns"]
        if before and before["configurable"].get("checkpoint_id"):
            params["avant"] = before["configurable"]["checkpoint_id"]
        if limit is not None and not filter:  # avec un filtre, la limite s'applique après
            params["limite"] = limit
        reponse = await self._appeler("GET", quote(fil, safe="") + "/liste", params=params)
        restant = limit
        for p in reponse.json()["points"]:
            if c.get("checkpoint_id") and p["checkpoint_id"] != c["checkpoint_id"]:
                continue
            tuple_ = self._tuple(fil, p)
            if filter and not all(tuple_.metadata.get(k) == v for k, v in filter.items()):
                continue
            if restant is not None:
                if restant <= 0:
                    return
                restant -= 1
            yield tuple_

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        c = config["configurable"]
        fil, ns = c["thread_id"], c["checkpoint_ns"]
        type_cp, octets_cp = self.serde.dumps_typed(checkpoint)
        type_meta, octets_meta = self.serde.dumps_typed(
            get_serializable_checkpoint_metadata(config, metadata)
        )
        await self._appeler(
            "PUT",
            quote(fil, safe=""),
            json={
                "ns": ns,
                "checkpoint_id": checkpoint["id"],
                "parent_id": c.get("checkpoint_id"),
                "type": type_cp,
                "checkpoint": _b64(octets_cp),
                "type_metadata": type_meta,
                "metadata": _b64(octets_meta),
            },
        )
        return {
            "configurable": {
                "thread_id": fil,
                "checkpoint_ns": ns,
                "checkpoint_id": checkpoint["id"],
            }
        }

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        if not writes:
            return
        c = config["configurable"]
        ecritures = []
        for i, (canal, valeur) in enumerate(writes):
            type_v, octets = self.serde.dumps_typed(valeur)
            ecritures.append(
                {
                    "idx": WRITES_IDX_MAP.get(canal, i),
                    "canal": canal,
                    "type": type_v,
                    "valeur": _b64(octets),
                }
            )
        await self._appeler(
            "PUT",
            quote(c["thread_id"], safe="") + "/ecritures",
            json={
                "ns": c.get("checkpoint_ns", ""),
                "checkpoint_id": c["checkpoint_id"],
                "task_id": task_id,
                "task_path": task_path,
                "ecritures": ecritures,
            },
        )

    async def adelete_thread(self, thread_id: str) -> None:
        await self._appeler("DELETE", quote(thread_id, safe=""))
