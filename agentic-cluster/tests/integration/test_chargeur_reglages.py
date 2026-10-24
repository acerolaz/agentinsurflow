"""TI — le chargeur lit agents.toml sur disque et contrôle les prompts réels."""

from pathlib import Path

import pytest

from agentinsurflow_cluster.domain.reglages import ReglageInvalide
from agentinsurflow_cluster.infrastructure.llm.reglages import charger_reglages

VALIDE = """
[{a}]
modele = "gpt-4.1-mini"
temperature = 0.0
max_tokens = 400
delai_s = 1.0
prompt = "{p}"
"""


def _ecrire(tmp_path: Path, prompt: str) -> Path:
    texte = "".join(
        VALIDE.format(a=a, p=prompt if a == "pieces" else f"{a}.md")
        for a in ("pieces", "analyste", "redacteur", "actuaire")
    )
    chemin = tmp_path / "agents.toml"
    chemin.write_text(texte, encoding="utf-8")
    return chemin


def test_fichier_du_depot_valide() -> None:
    reglages = charger_reglages(25.0)
    assert set(reglages) == {"pieces", "analyste", "redacteur", "actuaire"}
    assert reglages["pieces"].modele == "gpt-4.1-mini"


def test_toml_mal_forme(tmp_path: Path) -> None:
    chemin = tmp_path / "agents.toml"
    chemin.write_text("[pieces", encoding="utf-8")
    with pytest.raises(ReglageInvalide, match="agents.toml"):
        charger_reglages(25.0, chemin)


def test_prompt_inexistant(tmp_path: Path) -> None:
    with pytest.raises(ReglageInvalide):
        charger_reglages(25.0, _ecrire(tmp_path, "absent.md"))
