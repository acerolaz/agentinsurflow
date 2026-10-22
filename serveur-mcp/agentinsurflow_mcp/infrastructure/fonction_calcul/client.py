"""Adaptateur HTTP du port ``CalculateurPort`` : la Function de calcul (barème et formule).

Le client httpx n'est pas instrumenté : le ``traceparent`` est posé à la main. Aucun fait, résultat
ni corps de réponse n'entre dans une trace ou un log.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from azure.core.exceptions import AzureError
from opentelemetry import propagate
from opentelemetry.trace import Span
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from starlette.concurrency import run_in_threadpool

from ...domain.models import CALCUL_INDISPONIBLE, DONNEE_HORS_BAREME, ErreurOutil
from ..entra.application import credential_application
from ..otel.telemetrie import echec, tracer

journal = logging.getLogger(__name__)

DELAI = 10.0


class ConfigCalcul(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    calcul_url: str = "http://localhost:8000/api/calcul"  # via la gateway (D22)
    calcul_audience: str | None = None  # api://<appId calcul> : absent = calcul indisponible
    mcp_client_secret: SecretStr | None = None  # 🔒 .env local seulement
    azure_tenant_id: str | None = None
    mcp_api_client_id: str | None = None
    azure_uami_client_id: str | None = None


class ClientCalcul:
    def __init__(self, http: httpx.AsyncClient, cfg: ConfigCalcul) -> None:
        self._http, self._cfg = http, cfg
        self._base = cfg.calcul_url.rstrip("/")
        self._credential: Any = None

    async def evaluer(self, faits: dict[str, Any]) -> dict[str, Any]:
        return await self._appeler("/evaluer", "version_bareme", "bareme.version", faits)

    async def calculer(self, faits: dict[str, Any]) -> dict[str, Any]:
        return await self._appeler("/calculer", "version_formule", "formule.version", faits)

    async def _jeton(self) -> str:
        cfg = self._cfg
        if not cfg.calcul_audience:
            raise ErreurOutil(CALCUL_INDISPONIBLE, "Calcul non configuré (audience absente)")
        if self._credential is None:
            secret = cfg.mcp_client_secret.get_secret_value() if cfg.mcp_client_secret else None
            self._credential = credential_application(
                cfg.azure_tenant_id, cfg.mcp_api_client_id, secret, cfg.azure_uami_client_id
            )
        if self._credential is None:
            raise ErreurOutil(CALCUL_INDISPONIBLE, "Calcul non configuré (identité Entra absente)")
        try:
            portee = f"{cfg.calcul_audience}/.default"
            jeton: str = (await run_in_threadpool(self._credential.get_token, portee)).token
            return jeton
        except AzureError as exc:
            raise ErreurOutil(CALCUL_INDISPONIBLE, "Jeton du calcul refusé") from exc

    async def _appeler(
        self, route: str, cle_version: str, attribut_version: str, faits: dict[str, Any]
    ) -> dict[str, Any]:
        with tracer.start_as_current_span(
            "calcul.appeler",
            attributes={"calcul.route": route},
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                resultat = await self._envoyer(route, faits, span)
            except ErreurOutil as exc:
                span.set_attribute("resultat.code", exc.code)
                echec(span, exc.code)
                raise
            span.set_attribute("resultat.code", "OK")
            version = resultat.get(cle_version)
            if isinstance(version, str):
                span.set_attribute(attribut_version, version)
            return resultat

    async def _envoyer(self, route: str, faits: dict[str, Any], span: Span) -> dict[str, Any]:
        entetes = {"Authorization": f"Bearer {await self._jeton()}"}
        propagate.inject(entetes)
        try:
            reponse = await self._http.post(
                self._base + route, headers=entetes, json=faits, timeout=DELAI
            )
        except httpx.HTTPError as exc:
            raise ErreurOutil(CALCUL_INDISPONIBLE, "Calcul injoignable") from exc
        span.set_attribute("http.status_code", reponse.status_code)
        if reponse.status_code == 422:
            raise ErreurOutil(DONNEE_HORS_BAREME, f"Donnée hors barème : {_champ(reponse)}")
        if reponse.status_code == 400:
            journal.error("requête de calcul invalide")  # bug de contrat : jamais le corps
        if not reponse.is_success:
            raise ErreurOutil(CALCUL_INDISPONIBLE, f"Calcul : HTTP {reponse.status_code}")
        try:
            donnees = reponse.json()
        except ValueError as exc:
            raise ErreurOutil(CALCUL_INDISPONIBLE, "Réponse du calcul illisible") from exc
        if not isinstance(donnees, dict):
            raise ErreurOutil(CALCUL_INDISPONIBLE, "Réponse du calcul mal formée")
        return donnees


def _champ(reponse: httpx.Response) -> str:
    """Le nom du champ seul, s'il est un identifiant : jamais une valeur."""
    try:
        champ = reponse.json().get("champ")
    except (ValueError, AttributeError):
        return "inconnu"
    return champ if isinstance(champ, str) and champ.isidentifier() else "inconnu"
