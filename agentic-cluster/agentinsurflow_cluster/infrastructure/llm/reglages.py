"""Chargeur de `agents.toml` : lit le fichier, délègue la validation au domaine."""

import tomllib
from pathlib import Path

from agentinsurflow_cluster.domain.models import NomAgent
from agentinsurflow_cluster.domain.reglages import ReglageAgent, ReglageInvalide, valider_reglages
from agentinsurflow_cluster.infrastructure.llm.fabrique import PROMPTS

FICHIER_REGLAGES = Path(__file__).resolve().parents[3] / "agents.toml"


def charger_reglages(
    budget_global_s: float, chemin: Path = FICHIER_REGLAGES
) -> dict[NomAgent, ReglageAgent]:
    try:
        brut = tomllib.loads(chemin.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ReglageInvalide(f"{chemin.name} : {exc}") from exc
    return valider_reglages(brut, budget_global_s, lambda f: (PROMPTS / f).is_file())
