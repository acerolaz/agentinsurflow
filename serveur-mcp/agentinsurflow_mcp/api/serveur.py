"""Serveur MCP : ``FastMCP`` dont ``list_tools`` et ``call_tool`` sont filtrés par la matrice.

Le SDK enregistre ``self.list_tools`` et ``self.call_tool`` (``FastMCP._setup_handlers``) : les
surcharges sont donc celles que le protocole appelle. Le refus a lieu **avant** tout dispatch.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from mcp import types
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings

from ..application import outils
from ..domain.matrice import est_autorise, outils_autorises
from ..domain.models import UNAUTHORIZED_TOOL, Appelant, ErreurOutil
from ..domain.ports import CorpusPort, DossiersPort, JetonsPort
from .securite import appelant_courant


def _erreur(code: str, message: str) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=message)],
        structuredContent={"code": code},
        isError=True,
    )


class ServeurMcp(FastMCP):
    def __init__(
        self,
        jetons: JetonsPort,
        corpus: CorpusPort,
        dossiers: DossiersPort,
        nom: str = "agentinsurflow-mcp",
    ) -> None:
        super().__init__(
            nom,
            stateless_http=True,  # spec § 4 : aucune session côté serveur
            # derrière la gateway le Host n'est pas localhost ; la garde est le jeton Entra
            transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        )

        def appelant() -> Appelant:
            courant = appelant_courant.get()
            if courant is None:  # la garde ASGI l'a posé : défense en profondeur
                raise ErreurOutil(UNAUTHORIZED_TOOL, "Outil non autorisé")
            return courant

        @self.tool()
        async def search_rag(question: str, top_k: int | None = None) -> dict[str, Any]:
            """Cherche dans le corpus d'assurance les extraits cités qui répondent à la question.

            Renvoie les extraits avec leur citation (article, version, source) et leur score.
            Ne rédige aucune réponse : la rédaction reste à l'appelant. Renvoie l'erreur
            NOT_FOUND_IN_CORPUS plutôt qu'un extrait hors sujet quand aucun extrait n'est
            assez pertinent. `top_k` (1 à 20, facultatif) borne le nombre d'extraits.
            """
            return await outils.search_rag(appelant(), jetons, corpus, question, top_k)

        @self.tool()
        async def get_contrat(numero_contrat: str) -> dict[str, Any]:
            """Lit un contrat d'assurance auto : profil du conducteur, historique et formule.

            Lecture seule : ne modifie rien. Erreur CONTRAT_INTROUVABLE si le numéro est inconnu.
            """
            return await outils.get_contrat(appelant(), jetons, dossiers, numero_contrat)

    async def list_tools(self) -> list[types.Tool]:
        appelant = appelant_courant.get()
        permis = outils_autorises(appelant.agent if appelant else None)
        return [t for t in await super().list_tools() if t.name in permis]

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> Sequence[types.ContentBlock] | dict[str, Any]:
        appelant = appelant_courant.get()
        if not est_autorise(appelant.agent if appelant else None, name):
            return _erreur(UNAUTHORIZED_TOOL, "Outil non autorisé")  # type: ignore[return-value]
        try:
            return await super().call_tool(name, arguments)
        except ToolError as exc:
            if isinstance(exc.__cause__, ErreurOutil):
                return _erreur(exc.__cause__.code, str(exc.__cause__))  # type: ignore[return-value]
            raise
