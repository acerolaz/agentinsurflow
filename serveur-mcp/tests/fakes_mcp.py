"""Ports simulés du serveur MCP (``rag/tests/fakes.py`` est sur le même ``pythonpath``)."""

from __future__ import annotations

from typing import Any, Literal

from agentinsurflow_mcp.domain.models import Appelant, ErreurOutil


def appelant(agent: Literal["orchestrateur", "redacteur", "actuaire"] = "redacteur") -> Appelant:
    return Appelant("oid-a", "azp-a", agent, frozenset({"Gestionnaire"}), "jeton-entrant")


class FauxJetons:
    def __init__(self, refuse: bool = False) -> None:
        self.refuse = refuse
        self.demandes: list[tuple[str, str]] = []

    async def obo(self, appelant: Appelant, cible: Literal["rag", "underwriting"]) -> str:
        if self.refuse:
            raise ErreurOutil("DOSSIERS_INDISPONIBLES", "OBO refusé")
        self.demandes.append((appelant.jeton, cible))
        return f"obo-{cible}"


class FauxCorpus:
    def __init__(self, erreur: ErreurOutil | None = None) -> None:
        self.erreur = erreur
        self.appels: list[tuple[str, str, int | None]] = []

    async def chercher(self, jeton: str, question: str, top_k: int | None) -> dict[str, Any]:
        self.appels.append((jeton, question, top_k))
        if self.erreur:
            raise self.erreur
        return {"statut": "OK", "resultats": [{"texte": "extrait"}]}


VUE_SEED_1: dict[str, Any] = {
    "numero_contrat": "AIF-2026-000001",
    "suspensions": 0,
    "resiliations": 0,
    "crm_bonus_malus": 0.9,
    "departement": "75",
    "formule": "tous_risques",
    "date_effet": "2026-01-01",
    "anciennete_permis_mois": 91,
    "puissance_fiscale_cv": 5,
    "type_usage": "prive",
    "nb_sinistres_trois_ans": 0,
    "nb_sinistres_responsables_trois_ans": 0,
}


class FauxDossiers:
    def __init__(
        self, erreur: ErreurOutil | None = None, vue: dict[str, Any] | None = None
    ) -> None:
        self.erreur = erreur
        self.vue = vue
        self.appels: list[tuple[str, str]] = []
        self.ecritures: list[tuple[str, str, str, dict[str, Any]]] = []

    async def lire_contrat(self, jeton: str, numero_contrat: str) -> dict[str, Any]:
        self.appels.append((jeton, numero_contrat))
        if self.erreur:
            raise self.erreur
        return self.vue if self.vue is not None else {"numero_contrat": numero_contrat}

    async def enregistrer_brouillon(
        self, jeton: str, numero_contrat: str, corps: dict[str, Any]
    ) -> None:
        self.ecritures.append(("brouillon", jeton, numero_contrat, corps))
        if self.erreur:
            raise self.erreur

    async def changer_statut(self, jeton: str, numero_contrat: str, corps: dict[str, Any]) -> None:
        self.ecritures.append(("statut", jeton, numero_contrat, corps))
        if self.erreur:
            raise self.erreur


class FauxCalculateur:
    def __init__(self, erreur: ErreurOutil | None = None) -> None:
        self.erreur = erreur
        self.appels: list[tuple[str, dict[str, Any]]] = []

    async def evaluer(self, faits: dict[str, Any]) -> dict[str, Any]:
        self.appels.append(("evaluer", faits))
        if self.erreur:
            raise self.erreur
        return {"classe": "A", "decision": "ACCEPTE", "score": 0, "regles": []}

    async def calculer(self, faits: dict[str, Any]) -> dict[str, Any]:
        self.appels.append(("calculer", faits))
        if self.erreur:
            raise self.erreur
        return {"prime_ttc_annuelle": "819.73", "prime_mensuelle": "68.31"}
