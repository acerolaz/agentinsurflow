"""Fixtures E2E : la solution qui tourne (compose ou staging), toujours jointe par la gateway.

``E2E_URL`` désigne la gateway (défaut : le compose local). Les jetons viennent de
``E2E_JETON_GESTIONNAIRE`` / ``E2E_JETON_INGESTION`` (CI : OIDC), sinon de ``az account
get-access-token`` (lecture seule). Faute de jeton, le test est sauté avec la raison ; un jeton
n'est jamais affiché.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from urllib.parse import urlparse

import httpx
import pytest

HOTES_LOCAUX = {"localhost", "127.0.0.1", "::1"}


def _jeton(variable: str, application: str) -> str:
    if os.environ.get(variable):
        return os.environ[variable]
    try:
        sortie = subprocess.run(
            ["az", "account", "get-access-token", "--resource", f"api://{application}",
             "--query", "accessToken", "-o", "tsv"],
            capture_output=True, text=True, check=False, timeout=60,
        )  # fmt: skip
    except (OSError, subprocess.TimeoutExpired):
        sortie = None
    if sortie is None or sortie.returncode != 0 or not sortie.stdout.strip():
        pytest.skip(f"aucun jeton pour api://{application} : {variable} ou « az login » requis")
    return sortie.stdout.strip()


@pytest.fixture(scope="session")
def url() -> str:
    return os.environ.get("E2E_URL", "http://localhost:8000").rstrip("/")


@pytest.fixture(scope="session")
def local(url: str) -> bool:
    return urlparse(url).hostname in HOTES_LOCAUX


@pytest.fixture(scope="session")
def jeton_gestionnaire() -> str:
    """Rôle Gestionnaire, audience de rag (``POST /api/reponses``)."""
    return _jeton("E2E_JETON_GESTIONNAIRE", "agentinsurflow-rag")


@pytest.fixture(scope="session")
def jeton_gestionnaire_underwriting() -> str:
    """Rôle Gestionnaire, audience d'underwriting-admin (``/api/contrats``, ``/api/traces``)."""
    return _jeton("E2E_JETON_GESTIONNAIRE_UNDERWRITING", "agentinsurflow-underwriting")


@pytest.fixture(scope="session")
def jeton_ingestion() -> str:
    return _jeton("E2E_JETON_INGESTION", "agentinsurflow-rag")


@pytest.fixture(scope="session")
def client(url: str) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=url, timeout=120) as c:
        yield c
