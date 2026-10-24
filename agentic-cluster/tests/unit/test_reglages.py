"""TU — règles pures de validation du réglage par agent (aucune I/O)."""

from __future__ import annotations

import copy

import pytest

from agentinsurflow_cluster.domain.reglages import (
    AGENTS_REGLES,
    ReglageAgent,
    ReglageInvalide,
    valider_reglages,
)

VALIDE = {
    "pieces": {
        "modele": "gpt-4.1-mini",
        "temperature": 0.0,
        "max_tokens": 400,
        "delai_s": 1.5,
        "prompt": "pieces.md",
    },
    "analyste": {
        "modele": "gpt-4.1-mini",
        "temperature": 0.0,
        "max_tokens": 400,
        "delai_s": 2.0,
        "prompt": "analyste.md",
    },
    "redacteur": {
        "modele": "gpt-4.1-mini",
        "temperature": 0.2,
        "max_tokens": 1200,
        "delai_s": 8.0,
        "prompt": "redacteur.md",
    },
    "actuaire": {
        "modele": "gpt-4.1-mini",
        "temperature": 0.0,
        "max_tokens": 400,
        "delai_s": 1.5,
        "prompt": "actuaire.md",
    },
}


def existe(_fichier: str) -> bool:
    return True


def avec(agent: str, cle: str, valeur: object) -> dict:
    brut = copy.deepcopy(VALIDE)
    brut[agent][cle] = valeur
    return brut


def valider(brut, budget: float = 25.0, prompt_existe=existe):
    return valider_reglages(brut, budget, prompt_existe)


def test_reglages_valides_charges():
    r = valider(VALIDE)
    assert len(r) == 4
    assert tuple(r) == AGENTS_REGLES
    assert r["redacteur"] == ReglageAgent("gpt-4.1-mini", 0.2, 1200, 8.0, "redacteur.md")


def test_agent_manquant_refuse():
    brut = copy.deepcopy(VALIDE)
    del brut["actuaire"]
    with pytest.raises(ReglageInvalide, match="actuaire"):
        valider(brut)


def test_section_inconnue_refusee():
    brut = copy.deepcopy(VALIDE)
    brut["saga"] = dict(VALIDE["pieces"])
    with pytest.raises(ReglageInvalide, match="saga"):
        valider(brut)


def test_cle_inconnue_refusee():
    with pytest.raises(ReglageInvalide, match="pieces.*top_p|top_p.*pieces"):
        valider(avec("pieces", "top_p", 0.9))


def test_cle_manquante_refusee():
    brut = copy.deepcopy(VALIDE)
    del brut["pieces"]["modele"]
    with pytest.raises(ReglageInvalide, match="pieces.*modele|modele.*pieces"):
        valider(brut)


@pytest.mark.parametrize("t", [-0.1, 1.1, "0.5", True])
def test_temperature_hors_bornes_refusee(t):
    with pytest.raises(ReglageInvalide, match="temperature"):
        valider(avec("pieces", "temperature", t))


@pytest.mark.parametrize("t", [0, 1])
def test_temperature_aux_bornes_acceptee(t):
    assert isinstance(valider(avec("pieces", "temperature", t))["pieces"].temperature, float)


@pytest.mark.parametrize("m", [0, 16001, True, 1.5])
def test_max_tokens_refuse(m):
    with pytest.raises(ReglageInvalide, match="max_tokens"):
        valider(avec("pieces", "max_tokens", m))


@pytest.mark.parametrize("m", [1, 16000])
def test_max_tokens_aux_bornes_accepte(m):
    assert valider(avec("pieces", "max_tokens", m))["pieces"].max_tokens == m


@pytest.mark.parametrize("d", [0, -1])
def test_delai_non_positif_refuse(d):
    with pytest.raises(ReglageInvalide, match="delai_s"):
        valider(avec("pieces", "delai_s", d))


def test_modele_vide_refuse():
    with pytest.raises(ReglageInvalide, match="modele"):
        valider(avec("pieces", "modele", ""))


def test_somme_des_delais_egale_au_budget_acceptee():
    assert len(valider(VALIDE, budget=13.0)) == 4


def test_somme_des_delais_au_dela_refusee():
    with pytest.raises(ReglageInvalide, match="delai_s"):
        valider(VALIDE, budget=12.9)


@pytest.mark.parametrize("p", ["../x.md", "a/b.md", "a\\b.md"])
def test_prompt_avec_chemin_refuse(p):
    with pytest.raises(ReglageInvalide, match="prompt"):
        valider(avec("pieces", "prompt", p))


def test_prompt_absent_refuse():
    with pytest.raises(ReglageInvalide, match="prompt"):
        valider(VALIDE, prompt_existe=lambda f: False)


@pytest.mark.parametrize("v", [float("nan"), float("inf")])
def test_delai_non_fini_refuse(v):
    with pytest.raises(ReglageInvalide, match="pieces.*delai_s"):
        valider(avec("pieces", "delai_s", v), budget=float("inf"))


@pytest.mark.parametrize("v", [float("nan"), float("inf")])
def test_temperature_non_finie_refusee(v):
    with pytest.raises(ReglageInvalide, match="pieces.*temperature"):
        valider(avec("pieces", "temperature", v))


@pytest.mark.parametrize("section", [3, "x", None, ["a"]])
def test_section_non_table_refusee(section):
    brut = copy.deepcopy(VALIDE)
    brut["pieces"] = section
    with pytest.raises(ReglageInvalide, match="pieces"):
        valider(brut)
