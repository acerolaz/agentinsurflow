"""Serveur MCP : ``FastMCP`` dont ``list_tools`` et ``call_tool`` sont filtrés par la matrice.

Le SDK enregistre ``self.list_tools`` et ``self.call_tool`` (``FastMCP._setup_handlers``) : les
surcharges sont donc celles que le protocole appelle. Le refus a lieu **avant** tout dispatch.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Any, Literal

from mcp import types
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from opentelemetry.trace import Span

from ..application import outils
from ..domain.matrice import est_autorise, outils_autorises
from ..domain.models import UNAUTHORIZED_TOOL, Appelant, ErreurOutil, Fiche, PrimeBrouillon
from ..domain.ports import CorpusPort, DossiersPort, JetonsPort
from ..infrastructure.otel.telemetrie import echec, tracer
from .securite import appelant_courant

STATUTS_CONNUS = frozenset({"EN_ANALYSE", "REVUE_HUMAINE", "ACCEPTE", "REFUSE"})


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

        @self.tool()
        async def enregistrer_brouillon(
            numero_contrat: str, fiche: Fiche, prime: PrimeBrouillon | None = None
        ) -> dict[str, Any]:
            """Enregistre (ou remplace) la fiche de décision et la prime d'un contrat en brouillon.

            Ne change pas le statut du dossier : utiliser update_statut_dossier. `prime` est
            facultative ; `date_effet` au format AAAA-MM-JJ. Erreur CONTRAT_INTROUVABLE si le
            numéro est inconnu, ARGUMENTS_INVALIDES si le backend refuse la fiche ou la prime.
            """
            return await outils.enregistrer_brouillon(
                appelant(), jetons, dossiers, numero_contrat, fiche, prime
            )

        @self.tool()
        async def update_statut_dossier(
            numero_contrat: str,
            statut: Literal["EN_ANALYSE", "REVUE_HUMAINE", "ACCEPTE", "REFUSE"],
            validation: Literal["VALIDEE", "CORRIGEE"] | None = None,
        ) -> dict[str, Any]:
            """Change le statut d'un dossier (ex. REVUE_HUMAINE, ACCEPTE, REFUSE).

            ACCEPTE et REFUSE exigent `validation` (VALIDEE ou CORRIGEE) : sans elle le backend
            refuse et l'erreur est ARGUMENTS_INVALIDES. Erreur CONTRAT_INTROUVABLE si le numéro
            est inconnu.
            """
            return await outils.update_statut_dossier(
                appelant(), jetons, dossiers, numero_contrat, statut, validation
            )

    async def list_tools(self) -> list[types.Tool]:
        appelant = appelant_courant.get()
        with tracer.start_as_current_span("mcp.lister_outils") as span:
            permis = outils_autorises(appelant.agent if appelant else None)
            outils = [t for t in await super().list_tools() if t.name in permis]
            span.set_attributes(
                {"appelant.azp": appelant.azp if appelant else "", "outils.nombre": len(outils)}
            )
            return outils

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> Sequence[types.ContentBlock] | dict[str, Any]:
        appelant = appelant_courant.get()
        agent = appelant.agent if appelant else None
        azp = appelant.azp if appelant else ""
        with tracer.start_as_current_span(
            "mcp.outil", record_exception=False, set_status_on_exception=False
        ) as span:
            span.set_attributes({"mcp.outil": name, "appelant.azp": azp})
            _attributs_des_arguments(span, arguments)
            autorise = est_autorise(agent, name)
            span.set_attributes(
                {
                    "autorisation.decision": "allow" if autorise else "deny",
                    "autorisation.regle": f"matrice:{agent or 'inconnu'}",
                }
            )
            if not autorise:
                return _refus(span, UNAUTHORIZED_TOOL, "Outil non autorisé")  # type: ignore[return-value]
            try:
                resultat = await super().call_tool(name, arguments)
            except ToolError as exc:
                if isinstance(exc.__cause__, ErreurOutil):
                    return _refus(span, exc.__cause__.code, str(exc.__cause__))  # type: ignore[return-value]
                _erreur_inattendue(span)
                raise
            except Exception:
                _erreur_inattendue(span)
                raise
            span.set_attributes({"resultat.code": "OK", "isError": False})
            return resultat


def _erreur_inattendue(span: Span) -> None:
    span.set_attributes({"resultat.code": "ERREUR", "isError": True})
    echec(span, "ERREUR")


def _refus(span: Span, code: str, message: str) -> types.CallToolResult:
    span.set_attributes({"resultat.code": code, "isError": True})
    echec(span, code)
    return _erreur(code, message)


def _attributs_des_arguments(span: Span, arguments: dict[str, Any]) -> None:
    """Jamais la valeur d'un argument personnel : empreinte, longueur ou présence seulement."""
    question = arguments.get("question")
    if isinstance(question, str):
        span.set_attributes(
            {
                "question.sha256": hashlib.sha256(question.encode()).hexdigest(),
                "question.longueur": len(question),
            }
        )
    if "numero_contrat" in arguments:
        span.set_attribute("contrat.present", True)
    statut = arguments.get("statut")
    if statut is not None:  # une valeur saisie n'entre jamais dans la trace
        span.set_attribute(
            "statut.cible",
            statut if isinstance(statut, str) and statut in STATUTS_CONNUS else "INCONNU",
        )
