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
    assert tuple(r) == AGENTS_REGLES == ("pieces", "analyste", "redacteur", "actuaire")
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


# (agent, clé, valeur, budget) -> ReglageInvalide dont le message nomme l'agent et la clé
REFUS = [
    *[("pieces", "temperature", t, 25.0) for t in (-0.1, 1.1, "0.5", True)],
    *[("pieces", "temperature", v, 25.0) for v in (float("nan"), float("inf"), 10**400)],
    *[("pieces", "max_tokens", m, 25.0) for m in (0, 16001, True, 1.5)],
    *[("pieces", "delai_s", d, 25.0) for d in (0, -1)],
    *[("pieces", "delai_s", v, float("inf")) for v in (float("nan"), float("inf"))],
    ("pieces", "modele", "", 25.0),
    *[("pieces", "prompt", p, 25.0) for p in ("../x.md", "a/b.md", "a\\b.md")],
]


@pytest.mark.parametrize(("agent", "cle", "valeur", "budget"), REFUS)
def test_valeur_refusee(agent, cle, valeur, budget):
    with pytest.raises(ReglageInvalide, match=f"{agent}.*{cle}"):
        valider(avec(agent, cle, valeur), budget=budget)


@pytest.mark.parametrize(
    ("cle", "valeur", "attendu"),
    [
        ("temperature", 0, 0.0),
        ("temperature", 1, 1.0),
        ("max_tokens", 1, 1),
        ("max_tokens", 16000, 16000),
    ],
)
def test_valeur_aux_bornes_acceptee(cle, valeur, attendu):
    assert getattr(valider(avec("pieces", cle, valeur))["pieces"], cle) == attendu


def test_somme_des_delais_egale_au_budget_acceptee():
    assert len(valider(VALIDE, budget=13.0)) == 4


def test_somme_des_delais_au_dela_refusee():
    with pytest.raises(ReglageInvalide, match="delai_s"):
        valider(VALIDE, budget=12.9)


def test_delai_entier_geant_refuse_par_la_garde_globale():
    with pytest.raises(ReglageInvalide, match="somme"):
        valider(avec("pieces", "delai_s", 10**400))


def test_prompt_absent_refuse():
    with pytest.raises(ReglageInvalide, match="prompt"):
        valider(VALIDE, prompt_existe=lambda f: False)


@pytest.mark.parametrize("section", [3, "x", None, ["a"]])
def test_section_non_table_refusee(section):
    brut = copy.deepcopy(VALIDE)
    brut["pieces"] = section
    with pytest.raises(ReglageInvalide, match="pieces"):
        valider(brut)
