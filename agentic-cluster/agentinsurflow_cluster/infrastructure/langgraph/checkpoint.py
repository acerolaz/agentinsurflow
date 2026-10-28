"""Point de reprise du graphe (R15) : par la gateway (underwriting-admin, D106) ou mémoire (local).

Azure (``staging``, ``production``) : le saver HTTP est obligatoire, le démarrage échoue sans lui
(jamais de repli silencieux vers la mémoire). Jeton : même condition que l'export OTLP
(``creer_exportateur``), même audience (``TELEMETRIE_AUDIENCE`` = ``api://<underwriting>``).
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from langgraph.checkpoint.memory import MemorySaver

from ..entra.config import ConfigCluster
from ..entra.jetons import credential_application, source_assertion
from .checkpoint_http import CheckpointerHttp

journal = logging.getLogger(__name__)
ENVIRONNEMENTS_AZURE = ("staging", "production")


@asynccontextmanager
async def checkpointer(cfg: ConfigCluster | None = None, delai_s: float = 25) -> AsyncIterator[Any]:
    cfg = cfg or ConfigCluster()
    if cfg.telemetrie_audience and cfg.azure_tenant_id and cfg.insurflow_cluster_client_id:
        assertion = source_assertion(cfg)
        if assertion is not None:
            credential = credential_application(
                cfg.azure_tenant_id, cfg.insurflow_cluster_client_id, assertion
            )
            portee = f"{cfg.telemetrie_audience}/.default"
            # ponytail: un appel ne dépasse jamais le budget global d'une évaluation (garde) ;
            # à confirmer par la latence mesurée en staging (preuve K11)
            try:
                async with httpx.AsyncClient(base_url=cfg.gateway_url, timeout=delai_s) as client:
                    yield CheckpointerHttp(client, lambda: credential.get_token(portee).token)
            finally:
                credential.close()
            return
    env = os.environ.get("APP_ENV", "")
    if env in ENVIRONNEMENTS_AZURE:
        raise RuntimeError(
            f"points de reprise : configuration HTTP absente en {env} (TELEMETRIE_AUDIENCE, "
            "AZURE_TENANT_ID, INSURFLOW_CLUSTER_CLIENT_ID et une source d'assertion) ; "
            "pas de repli vers la mémoire"
        )
    journal.warning("points de reprise en mémoire (perdus au redémarrage) : pas de jeton configuré")
    yield MemorySaver()
