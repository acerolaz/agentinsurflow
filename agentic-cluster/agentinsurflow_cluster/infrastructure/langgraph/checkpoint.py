"""Point de reprise du graphe (R15) : PostgreSQL (schéma ``agent_state``) ou mémoire (tests)."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from langgraph.checkpoint.memory import MemorySaver

journal = logging.getLogger(__name__)
SCHEMA = "agent_state"


@asynccontextmanager
async def checkpointer(dsn: str | None = None) -> AsyncIterator[Any]:
    """``AsyncPostgresSaver`` si ``INSURFLOW_CHECKPOINT_DSN`` est posé, sinon ``MemorySaver``."""
    dsn = dsn if dsn is not None else os.environ.get("INSURFLOW_CHECKPOINT_DSN")
    if not dsn:
        journal.warning(
            "INSURFLOW_CHECKPOINT_DSN absent : points de reprise en mémoire (perdus au redémarrage)"
        )
        yield MemorySaver()
        return
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import AsyncConnectionPool

    options = f"-c search_path={SCHEMA}"
    async with AsyncConnectionPool(
        dsn,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row,
                "options": options},
        open=False,
    ) as pool:  # fmt: skip
        async with pool.connection() as connexion:
            # Azure : schéma posé par infra/postgres/init.sh, compte sans droit de créer un schéma
            # (CREATE SCHEMA IF NOT EXISTS vérifie ce droit même si le schéma existe)
            cur = await connexion.execute(
                "SELECT 1 FROM pg_namespace WHERE nspname = %s", (SCHEMA,)
            )
            if await cur.fetchone() is None:
                await connexion.execute(f"CREATE SCHEMA {SCHEMA}")
        saver = AsyncPostgresSaver(pool)  # type: ignore[arg-type]
        await saver.setup()
        yield saver
