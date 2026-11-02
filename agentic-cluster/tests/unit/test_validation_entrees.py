"""Unitaires — règles d'entrée de l'API : jeton Entra (PyJWT, clé locale) et motif de revue."""

from __future__ import annotations

import pytest
from jetons_cluster_de_test import (
    CLE_PUBLIQUE,
    CLIENT_CLUSTER,
    EMETTEUR_V1,
    config_cluster,
    creer,
)
from pydantic import ValidationError

from agentinsurflow_cluster.api.schemas import RevueCorps
from agentinsurflow_cluster.infrastructure.entra.verification import verifier_jeton


@pytest.mark.parametrize("aud", [CLIENT_CLUSTER, f"api://{CLIENT_CLUSTER}"])
def test_audience_appid_et_emetteur_v1_acceptes(aud: str) -> None:
    g = verifier_jeton(creer(aud=aud, iss=EMETTEUR_V1), CLE_PUBLIQUE, config_cluster())
    assert "Gestionnaire" in g.roles


@pytest.mark.parametrize("motif", ["", "x" * 501])
def test_motif_de_1_a_500_caracteres(motif: str) -> None:
    with pytest.raises(ValidationError):
        RevueCorps(decision="ACCEPTE", validation="VALIDEE", motif=motif)
