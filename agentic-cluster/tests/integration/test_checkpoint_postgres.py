"""TI — point de reprise PostgreSQL (compose, base dossiers_test, compte agent_state)."""

import os

import psycopg
import pytest

from agentinsurflow_cluster.infrastructure.langgraph.checkpoint import checkpointer

pytestmark = pytest.mark.skipif(
    not os.environ.get("PG_AGENT_STATE_PASSWORD"), reason="PostgreSQL du compose absent"
)
DSN = (
    f"postgresql://agent_state:{os.environ.get('PG_AGENT_STATE_PASSWORD', '')}"
    f"@{os.environ.get('PG_HOST', 'localhost')}:{os.environ.get('PG_PORT', '5432')}/dossiers_test"
)
CONFIG = {"configurable": {"thread_id": "AIF-TEST", "checkpoint_ns": ""}}


async def test_connexions_fermees_par_le_serveur_remplacees() -> None:
    # Staging, 26/10 : la base annexe a changé de révision pendant le déploiement ; le pool rendait
    # des connexions fermées côté serveur (OperationalError ⇒ 500 sur /evaluation).
    async with checkpointer(DSN) as saver:
        assert await saver.aget_tuple(CONFIG) is None
        async with await psycopg.AsyncConnection.connect(DSN, autocommit=True) as admin:
            await admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity"
                " WHERE usename = 'agent_state' AND pid <> pg_backend_pid()"
            )
        assert await saver.aget_tuple(CONFIG) is None
