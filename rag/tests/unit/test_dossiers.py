"""Unitaires — accès aux dossiers chez underwriting-admin : client HTTP (simulé en mémoire),
jeton On-Behalf-Of, cas d'usage (contrat absent ou d'un autre gestionnaire : même 404).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest
from azure.core.exceptions import ClientAuthenticationError

from agentinsurflow_rag.application.use_cases.consulter_contrat import consulter_contrat
from agentinsurflow_rag.domain.models import VueContrat
from agentinsurflow_rag.domain.ports import ContratIntrouvable, ErreurDossiers
from agentinsurflow_rag.infrastructure.entra import obo
from agentinsurflow_rag.infrastructure.underwriting.client import ClientUnderwriting

VUE = {
    "numero_contrat": "AIF-2026-0001",
    "tranche_age": "25-34",
    "anciennete_permis_ans": 6,
    "departement": "69",
    "crm_bonus_malus": 0.85,
    "nb_sinistres": 1,
    "suspensions": 0,
    "resiliations": 0,
    "formule": "tous risques",
    "mis_a_jour": "2026-09-01T00:00:00Z",
}


async def _jeton() -> str:
    return "jeton-obo"


def _client(repondre: Callable[[httpx.Request], httpx.Response]) -> ClientUnderwriting:
    http = httpx.AsyncClient(transport=httpx.MockTransport(repondre))
    return ClientUnderwriting(http, "http://underwriting:8002", _jeton)


async def test_contrat_lu_avec_le_jeton_obo() -> None:
    recu: list[httpx.Request] = []

    def repondre(requete: httpx.Request) -> httpx.Response:
        recu.append(requete)
        return httpx.Response(200, json=VUE)

    contrat = await _client(repondre).lire_contrat("AIF-2026-0001")
    assert isinstance(contrat, VueContrat) and contrat.crm_bonus_malus == 0.85
    assert recu[0].url.path == "/api/contrats/AIF-2026-0001"
    assert recu[0].headers["authorization"] == "Bearer jeton-obo"


async def test_contrat_absent_404_rend_none() -> None:
    assert await _client(lambda r: httpx.Response(404)).lire_contrat("AIF-X") is None


@pytest.mark.parametrize("statut", [401, 403, 500, 503])
async def test_autre_statut_erreur_dossiers(statut: int) -> None:
    with pytest.raises(ErreurDossiers):
        await _client(lambda r: httpx.Response(statut)).lire_contrat("AIF-X")


async def test_underwriting_injoignable_erreur_dossiers() -> None:
    def panne(requete: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refusé", request=requete)

    with pytest.raises(ErreurDossiers):
        await _client(panne).lire_contrat("AIF-X")


async def test_reponse_mal_formee_erreur_dossiers() -> None:
    with pytest.raises(ErreurDossiers):
        await _client(lambda r: httpx.Response(200, json={"numero_contrat": "X"})).lire_contrat("X")


async def test_numero_echappe_dans_l_url() -> None:
    recu: list[httpx.Request] = []

    def repondre(requete: httpx.Request) -> httpx.Response:
        recu.append(requete)
        return httpx.Response(404)

    await _client(repondre).lire_contrat("../traces")
    assert recu[0].url.raw_path == b"/api/contrats/..%2Ftraces"


# ---------------------------------------------------------------- cas d'usage


class _Dossiers:
    def __init__(self, vue: VueContrat | None) -> None:
        self.vue = vue

    async def lire_contrat(self, numero_contrat: str) -> VueContrat | None:
        return self.vue


async def test_contrat_absent_ou_d_un_autre_gestionnaire_meme_erreur() -> None:
    # underwriting-admin rend 404 dans les deux cas (BOLA) : rag ne peut pas les distinguer
    with pytest.raises(ContratIntrouvable):
        await consulter_contrat(_Dossiers(None), "AIF-2026-0002")


async def test_dossiers_non_configures_erreur_dossiers() -> None:
    with pytest.raises(ErreurDossiers):
        await consulter_contrat(None, "AIF-2026-0001")


# ---------------------------------------------------------------- jeton On-Behalf-Of


class _Credential:
    appels: list[dict[str, Any]] = []
    erreur: Exception | None = None

    def __init__(self, tenant_id: str, client_id: str, **options: Any) -> None:
        _Credential.appels.append({"tenant_id": tenant_id, "client_id": client_id, **options})

    def get_token(self, *portees: str) -> Any:
        if _Credential.erreur:
            raise _Credential.erreur
        _Credential.appels[-1]["portees"] = portees
        return type("Jeton", (), {"token": "jeton-obo"})()


def _config(**valeurs: str) -> obo.ConfigObo:
    defaut = {
        "azure_tenant_id": "tenant",
        "rag_api_client_id": "rag",
        "underwriting_api_client_id": "uw",
        "rag_client_secret": "secret-local",
    }
    return obo.ConfigObo(_env_file=None, **{**defaut, **valeurs})  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _sans_entra(monkeypatch: pytest.MonkeyPatch) -> None:
    _Credential.appels, _Credential.erreur = [], None
    monkeypatch.setattr(obo, "OnBehalfOfCredential", _Credential)


def test_obo_en_local_avec_le_secret() -> None:
    assert obo.jeton_obo(_config(), "jeton-utilisateur") == "jeton-obo"
    (appel,) = _Credential.appels
    assert (
        appel["user_assertion"] == "jeton-utilisateur" and appel["client_secret"] == "secret-local"
    )
    assert appel["portees"] == ("api://uw/access_as_user",)


def test_obo_en_azure_avec_l_identite_managee() -> None:
    obo.jeton_obo(_config(rag_client_secret="", azure_uami_client_id="uami"), "jeton-utilisateur")
    (appel,) = _Credential.appels
    assert "client_secret" not in appel and callable(appel["client_assertion_func"])


def test_obo_sans_secret_ni_identite_erreur_dossiers() -> None:
    with pytest.raises(ErreurDossiers):
        obo.jeton_obo(_config(rag_client_secret=""), "jeton-utilisateur")


def test_obo_refuse_erreur_dossiers() -> None:
    _Credential.erreur = ClientAuthenticationError("consentement manquant")
    with pytest.raises(ErreurDossiers):
        obo.jeton_obo(_config(), "jeton-utilisateur")
