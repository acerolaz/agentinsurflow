"""Matrice d'accès : les outils permis à chaque agent, identifié par son ``azp``."""

from __future__ import annotations

from collections.abc import Mapping

from .models import Agent

MATRICE: Mapping[Agent, frozenset[str]] = {
    "saga": frozenset(
        {"get_contrat", "enregistrer_brouillon", "update_statut_dossier", "enregistrer_etat"}
    ),
    "pieces": frozenset({"lister_pieces"}),
    "analyste": frozenset({"evaluer_risque"}),
    "redacteur": frozenset({"search_rag"}),
    "actuaire": frozenset({"calculer_prime"}),
}


def outils_autorises(agent: Agent | None) -> frozenset[str]:
    return MATRICE[agent] if agent is not None else frozenset()


def est_autorise(agent: Agent | None, outil: str) -> bool:
    return outil in outils_autorises(agent)
