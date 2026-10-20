"""Unitaires — validation d'un jeton Entra ID (signature, émetteur, audience, expiration)."""

from __future__ import annotations

from typing import Any

import pytest

from agentinsurflow_rag.domain.models import Appelant
from agentinsurflow_rag.infrastructure.entra.jetons import ConfigAuth, ErreurAuth, verifier_jeton
from jetons_de_test import (
    CLE_ETRANGERE,
    CLE_PUBLIQUE,
    CLIENT_ID,
    EMETTEUR_V1,
    TENANT,
    creer,
)

CFG = ConfigAuth(_env_file=None, azure_tenant_id=TENANT, rag_api_client_id=CLIENT_ID)  # type: ignore[call-arg]

DEFAUTS: dict[str, dict[str, Any]] = {
    "expire": {"expire_dans": -120},
    "autre_tenant": {"iss": "https://login.microsoftonline.com/autre-tenant/v2.0"},
    "autre_audience": {"aud": "api://agentinsurflow-underwriting"},
    "signature_etrangere": {"cle": CLE_ETRANGERE},
}


@pytest.mark.parametrize("defaut", DEFAUTS)
def test_jeton_refuse(defaut: str) -> None:
    with pytest.raises(ErreurAuth):
        verifier_jeton(creer(**DEFAUTS[defaut]), CLE_PUBLIQUE, CFG)


def test_jeton_mal_forme_refuse() -> None:
    with pytest.raises(ErreurAuth):
        verifier_jeton("pas-un-jwt", CLE_PUBLIQUE, CFG)


def test_jeton_sans_oid_refuse() -> None:
    with pytest.raises(ErreurAuth):
        verifier_jeton(creer(oid=""), CLE_PUBLIQUE, CFG)


def test_jeton_v1_accepte_avec_audience_api() -> None:
    appelant = verifier_jeton(creer(iss=EMETTEUR_V1, aud=f"api://{CLIENT_ID}"), CLE_PUBLIQUE, CFG)
    assert appelant.oid == "oid-gestionnaire-a"


def test_audiences_partagees_avec_la_gateway() -> None:
    # RAG_API_AUDIENCES : une seule liste, lue par rag et par la gateway (I5)
    cfg = ConfigAuth(
        _env_file=None,  # type: ignore[call-arg]
        azure_tenant_id=TENANT,
        rag_api_client_id=CLIENT_ID,
        rag_api_audiences=f" {CLIENT_ID}, api://agentinsurflow-rag ",
    )
    assert cfg.audiences == [CLIENT_ID, "api://agentinsurflow-rag"]
    assert verifier_jeton(creer(aud="api://agentinsurflow-rag"), CLE_PUBLIQUE, cfg).oid


def test_appelant_porte_oid_et_roles() -> None:
    appelant = verifier_jeton(creer(["Gestionnaire", "Ingestion"], oid="oid-x"), CLE_PUBLIQUE, CFG)
    assert appelant == Appelant(oid="oid-x", roles=frozenset({"Gestionnaire", "Ingestion"}))


def test_sans_roles_appelant_sans_role() -> None:
    assert verifier_jeton(creer([]), CLE_PUBLIQUE, CFG).roles == frozenset()
