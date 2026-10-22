"""Unitaires — faits tirés de la vue du contrat et cas d'usage des outils de calcul."""

from __future__ import annotations

import pytest
from fakes_mcp import VUE_SEED_1, FauxCalculateur, FauxDossiers, FauxJetons, appelant

from agentinsurflow_mcp.application.outils import calculer_prime, evaluer_risque
from agentinsurflow_mcp.domain.faits import faits_prime, faits_risque
from agentinsurflow_mcp.domain.models import CONTRAT_INTROUVABLE, ErreurOutil


def test_faits_risque_depuis_la_vue() -> None:
    assert faits_risque(VUE_SEED_1) == {
        "suspensions": 0,
        "resiliations": 0,
        "crm": "0.9",
        "nb_sinistres_responsables_trois_ans": 0,
        "nb_sinistres_trois_ans": 0,
        "anciennete_permis_mois": 91,
        "puissance_fiscale_cv": 5,
    }


def test_faits_prime_depuis_la_vue() -> None:
    assert faits_prime(VUE_SEED_1) == {
        "formule": "tous_risques",
        "anciennete_permis_mois": 91,
        "departement": "75",
        "puissance_fiscale_cv": 5,
        "type_usage": "prive",
        "crm": "0.9",
    }


@pytest.mark.parametrize("avec_none", [False, True])
def test_fait_absent_ou_none_vaut_none(avec_none: bool) -> None:
    vue = {k: v for k, v in VUE_SEED_1.items() if k not in ("puissance_fiscale_cv", "type_usage")}
    if avec_none:
        vue |= {"puissance_fiscale_cv": None, "type_usage": None}
    assert faits_risque(vue)["puissance_fiscale_cv"] is None
    assert faits_prime(vue)["puissance_fiscale_cv"] is None
    assert faits_prime(vue)["type_usage"] is None


def test_crm_absent_reste_none() -> None:
    assert faits_risque({})["crm"] is None
    assert faits_prime({"crm_bonus_malus": None})["crm"] is None


async def test_evaluer_risque_obo_lecture_puis_calcul() -> None:
    jetons, dossiers, calc = FauxJetons(), FauxDossiers(vue=VUE_SEED_1), FauxCalculateur()
    resultat = await evaluer_risque(appelant(), jetons, dossiers, calc, "AIF-2026-000001")
    assert jetons.demandes == [("jeton-entrant", "underwriting")]
    assert dossiers.appels == [("obo-underwriting", "AIF-2026-000001")]
    assert calc.appels == [("evaluer", faits_risque(VUE_SEED_1))]
    assert resultat["decision"] == "ACCEPTE"


async def test_calculer_prime_obo_lecture_puis_calcul() -> None:
    jetons, dossiers, calc = FauxJetons(), FauxDossiers(vue=VUE_SEED_1), FauxCalculateur()
    resultat = await calculer_prime(appelant(), jetons, dossiers, calc, "AIF-2026-000001")
    assert jetons.demandes == [("jeton-entrant", "underwriting")]
    assert calc.appels == [("calculer", faits_prime(VUE_SEED_1))]
    assert resultat["prime_ttc_annuelle"] == "819.73"


@pytest.mark.parametrize("cas_usage", [evaluer_risque, calculer_prime])
async def test_contrat_introuvable_propage_sans_calcul(cas_usage) -> None:  # type: ignore[no-untyped-def]
    calc = FauxCalculateur()
    dossiers = FauxDossiers(ErreurOutil(CONTRAT_INTROUVABLE, "x"))
    with pytest.raises(ErreurOutil) as exc:
        await cas_usage(appelant(), FauxJetons(), dossiers, calc, "X")
    assert exc.value.code == CONTRAT_INTROUVABLE
    assert calc.appels == []
