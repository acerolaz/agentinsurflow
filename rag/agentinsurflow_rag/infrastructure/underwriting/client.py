"""Adaptateur HTTP du port ``DepotDossiers`` : ``GET /api/contrats/{numero_contrat}`` chez
underwriting-admin, avec le jeton On-Behalf-Of du gestionnaire et le ``traceparent`` courant.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from urllib.parse import quote

import httpx
from opentelemetry import propagate

from ...domain.models import VueContrat
from ...domain.ports import ErreurDossiers


class ClientUnderwriting:
    def __init__(
        self, http: httpx.AsyncClient, base_url: str, jeton_obo: Callable[[], Awaitable[str]]
    ) -> None:
        self._http, self._base, self._jeton_obo = http, base_url.rstrip("/"), jeton_obo

    async def lire_contrat(self, numero_contrat: str) -> VueContrat | None:
        entetes = {"Authorization": f"Bearer {await self._jeton_obo()}"}
        propagate.inject(entetes)  # une seule trace : rag → underwriting-admin
        url = f"{self._base}/api/contrats/{quote(numero_contrat, safe='')}"
        try:
            reponse = await self._http.get(url, headers=entetes)
        except httpx.HTTPError as exc:
            raise ErreurDossiers(f"underwriting-admin injoignable : {exc!r}") from exc
        if reponse.status_code == 404:
            return None
        if reponse.status_code != 200:
            raise ErreurDossiers(f"underwriting-admin a répondu {reponse.status_code}")
        try:
            vue = reponse.json()
            return VueContrat(
                numero_contrat=str(vue["numero_contrat"]),
                tranche_age=str(vue["tranche_age"]),
                anciennete_permis_ans=int(vue["anciennete_permis_ans"]),
                departement=str(vue["departement"]),
                crm_bonus_malus=float(vue["crm_bonus_malus"]),
                nb_sinistres=int(vue["nb_sinistres"]),
                suspensions=int(vue["suspensions"]),
                resiliations=int(vue["resiliations"]),
                formule=str(vue["formule"]),
                mis_a_jour=datetime.fromisoformat(str(vue["mis_a_jour"])),
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise ErreurDossiers(f"vue du contrat mal formée : {exc!r}") from exc
