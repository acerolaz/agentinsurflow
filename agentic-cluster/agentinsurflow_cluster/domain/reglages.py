"""Réglage par agent et règles de validation (pures : aucune I/O, stdlib seulement)."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import get_args

from agentinsurflow_cluster.domain.models import NomAgent

AGENTS_REGLES: tuple[NomAgent, ...] = get_args(NomAgent)  # une seule source des noms d'agents
CLES = ("modele", "temperature", "max_tokens", "delai_s", "prompt")
MAX_TOKENS_PLAFOND = 16_000


class ReglageInvalide(ValueError):
    """Réglage refusé ; le message nomme l'agent et la clé."""


@dataclass(frozen=True)
class ReglageAgent:
    modele: str
    temperature: float
    max_tokens: int
    delai_s: float
    prompt: str


def _nombre(valeur: object) -> bool:
    """Entier ou flottant fini (``isfinite`` sur les seuls flottants : un entier géant déborde)."""
    return (
        isinstance(valeur, int)
        and not isinstance(valeur, bool)
        or (isinstance(valeur, float) and math.isfinite(valeur))
    )


def _flottant(valeur: float) -> float:
    try:
        return float(valeur)
    except OverflowError:  # entier géant : la garde globale le refusera
        return math.inf


def _refus(agent: str, cle: str, raison: str) -> ReglageInvalide:
    return ReglageInvalide(f"réglage de l'agent « {agent} », clé « {cle} » : {raison}")


def _valider_agent(
    agent: str, section: Mapping[str, object], prompt_existe: Callable[[str], bool]
) -> ReglageAgent:
    if not isinstance(section, Mapping):
        raise ReglageInvalide(f"section « {agent} » : table attendue")
    for cle in section:
        if cle not in CLES:
            raise _refus(agent, str(cle), "clé inconnue")
    for cle in CLES:
        if cle not in section:
            raise _refus(agent, cle, "clé manquante")
    modele, temperature = section["modele"], section["temperature"]
    max_tokens, delai_s, prompt = section["max_tokens"], section["delai_s"], section["prompt"]
    if not isinstance(modele, str) or not modele.strip():
        raise _refus(agent, "modele", "texte non vide attendu")
    if not _nombre(temperature) or not 0 <= temperature <= 1:  # type: ignore[operator]
        raise _refus(agent, "temperature", "nombre attendu dans [0, 1]")
    if (
        not isinstance(max_tokens, int)
        or isinstance(max_tokens, bool)
        or not 1 <= max_tokens <= MAX_TOKENS_PLAFOND
    ):
        raise _refus(agent, "max_tokens", f"entier attendu dans [1, {MAX_TOKENS_PLAFOND}]")
    if not _nombre(delai_s) or delai_s <= 0:  # type: ignore[operator]
        raise _refus(agent, "delai_s", "nombre strictement positif attendu")
    if not isinstance(prompt, str) or not prompt or any(m in prompt for m in ("/", "\\", "..")):
        raise _refus(agent, "prompt", "nom de fichier simple attendu (sans chemin)")
    if not prompt_existe(prompt):
        raise _refus(agent, "prompt", f"fichier « {prompt} » introuvable")
    return ReglageAgent(modele, float(temperature), max_tokens, _flottant(delai_s), prompt)  # type: ignore[arg-type]


def valider_reglages(
    brut: Mapping[str, Mapping[str, object]],
    budget_global_s: float,
    prompt_existe: Callable[[str], bool],
) -> dict[NomAgent, ReglageAgent]:
    for nom in brut:
        if nom not in AGENTS_REGLES:
            raise ReglageInvalide(
                f"section « {nom} » inconnue (agents réglés : {', '.join(AGENTS_REGLES)})"
            )
    for nom in AGENTS_REGLES:
        if nom not in brut:
            raise ReglageInvalide(f"section « {nom} » manquante")
    reglages = {nom: _valider_agent(nom, brut[nom], prompt_existe) for nom in AGENTS_REGLES}
    somme = sum(r.delai_s for r in reglages.values())
    if somme > budget_global_s:
        raise ReglageInvalide(
            f"somme des delai_s ({somme}) supérieure à la garde globale ({budget_global_s} s)"
        )
    return reglages
