"""Mesure des garde-fous d'entrée (``make garde-fous``) : rejoue ``eval/garde-fous/*.jsonl``
dans ``ScannersLlmGuard.entree`` et imprime le taux de blocage par catégorie hostile et le taux
de faux positifs des observations légitimes. Jamais le texte des observations : des ids seulement.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict

from agentinsurflow_cluster.infrastructure.garde_fous.llm_guard import ScannersLlmGuard

_RACINE = Path(__file__).resolve().parents[1]
_JEU = _RACINE / "eval" / "garde-fous"
_ENV = _RACINE / "agentic-cluster" / "garde_fous.env"


class _Plafond(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV, env_ignore_empty=True, extra="ignore")
    plafond_faux_positifs: float = 0.0


def plafond_faux_positifs() -> float:
    """Plafond mesuré (pas une cible) de ``garde_fous.env``, en fraction."""
    return _Plafond().plafond_faux_positifs


def charger_jeu(nom: str) -> list[dict[str, Any]]:
    lignes = (_JEU / f"{nom}.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(ligne) for ligne in lignes if ligne.strip()]


@dataclass(frozen=True)
class Mesure:
    hostiles: list[dict[str, Any]]  # lignes + `codes`
    legitimes: list[dict[str, Any]]

    @property
    def taux_blocage(self) -> dict[str, float]:
        par: dict[str, list[bool]] = defaultdict(list)
        for ligne in self.hostiles:
            par[ligne["categorie"]].append(bool(ligne["codes"]))
        return {c: sum(v) / len(v) for c, v in par.items()}

    @property
    def faux_positifs(self) -> list[str]:
        return [ligne["id"] for ligne in self.legitimes if ligne["codes"]]

    @property
    def taux_faux_positifs(self) -> float:
        return len(self.faux_positifs) / len(self.legitimes)


def mesurer(
    garde: ScannersLlmGuard, hostiles: list[dict[str, Any]], legitimes: list[dict[str, Any]]
) -> Mesure:
    def passer(lignes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{**ligne, "codes": garde.entree(ligne["observations"])} for ligne in lignes]

    return Mesure(passer(hostiles), passer(legitimes))


def main() -> None:
    m = mesurer(ScannersLlmGuard(), charger_jeu("hostiles"), charger_jeu("legitimes"))
    for categorie, taux in m.taux_blocage.items():
        print(f"{categorie:15} blocage {taux:6.1%}")
    non = [ligne["id"] for ligne in m.hostiles if not ligne["codes"]]
    print(f"hostiles non détectés (neutralisation seule) : {', '.join(non) or 'aucun'}")
    print(f"faux positifs : {m.taux_faux_positifs:.1%} ({', '.join(m.faux_positifs) or 'aucun'})")
    plafond = math.ceil(m.taux_faux_positifs * 20) / 20
    print(f"plafond mesuré à consigner (PLAFOND_FAUX_POSITIFS) : {plafond:.2f}")


if __name__ == "__main__":
    main()
