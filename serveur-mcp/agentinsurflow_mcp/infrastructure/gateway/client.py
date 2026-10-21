"""Adaptateur HTTP des ports ``CorpusPort`` et ``DossiersPort`` : tout passe par la gateway (D22).

Le client httpx n'est pas instrumenté (comme rag) : le ``traceparent`` est posé à la main.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from ...domain.models import (
    ARGUMENTS_INVALIDES,
    CONTRAT_INTROUVABLE,
    DOSSIERS_INDISPONIBLES,
    NOT_FOUND_IN_CORPUS,
    ErreurOutil,
)


class ClientGateway:
    def __init__(self, http: httpx.AsyncClient, gateway_url: str) -> None:
        self._http, self._base = http, gateway_url.rstrip("/")

    async def chercher(self, jeton: str, question: str, top_k: int | None) -> dict[str, Any]:
        params: dict[str, Any] = {"question": question}
        if top_k is not None:
            params["top_k"] = top_k
        resultat = await self._appeler(
            "GET", "/api/extraits", jeton, NOT_FOUND_IN_CORPUS, params=params
        )
        if resultat.get("statut") == NOT_FOUND_IN_CORPUS:
            raise ErreurOutil(NOT_FOUND_IN_CORPUS, "Aucun extrait pertinent dans le corpus")
        return resultat

    async def lire_contrat(self, jeton: str, numero_contrat: str) -> dict[str, Any]:
        return await self._appeler("GET", self._contrat(numero_contrat), jeton, CONTRAT_INTROUVABLE)

    async def enregistrer_brouillon(
        self, jeton: str, numero_contrat: str, corps: dict[str, Any]
    ) -> None:
        chemin = f"{self._contrat(numero_contrat)}/brouillon"
        await self._appeler("PUT", chemin, jeton, CONTRAT_INTROUVABLE, corps=corps)

    async def changer_statut(self, jeton: str, numero_contrat: str, corps: dict[str, Any]) -> None:
        chemin = f"{self._contrat(numero_contrat)}/statut"
        await self._appeler("PUT", chemin, jeton, CONTRAT_INTROUVABLE, corps=corps)

    @staticmethod
    def _contrat(numero_contrat: str) -> str:
        return f"/api/contrats/{quote(numero_contrat, safe='')}"

    async def _appeler(
        self,
        methode: str,
        chemin: str,
        jeton: str,
        code_404: str,
        *,
        params: dict[str, Any] | None = None,
        corps: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        entetes = {"Authorization": f"Bearer {jeton}"}
        # T7 : propagate.inject(entetes) — une seule trace agent → MCP → gateway → backend
        try:
            reponse = await self._http.request(
                methode, self._base + chemin, headers=entetes, params=params, json=corps
            )
        except httpx.HTTPError as exc:
            raise ErreurOutil(DOSSIERS_INDISPONIBLES, "Gateway injoignable") from exc
        if reponse.status_code == 404:
            raise ErreurOutil(code_404, "Ressource introuvable")
        if reponse.status_code in (400, 422):
            raise ErreurOutil(ARGUMENTS_INVALIDES, "Arguments refusés par le backend")
        if not reponse.is_success:
            raise ErreurOutil(DOSSIERS_INDISPONIBLES, f"Gateway : HTTP {reponse.status_code}")
        if not reponse.content:
            return {}
        try:
            donnees = reponse.json()
        except ValueError as exc:
            raise ErreurOutil(DOSSIERS_INDISPONIBLES, "Réponse de la gateway illisible") from exc
        if not isinstance(donnees, dict):
            raise ErreurOutil(DOSSIERS_INDISPONIBLES, "Réponse de la gateway mal formée")
        return donnees
