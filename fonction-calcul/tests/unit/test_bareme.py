"""Barème déterministe ``evaluer`` : règles R01→R06, bornes, données absentes."""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

from agentinsurflow_calcul.domain.bareme import REGLES, Condition, evaluer
from agentinsurflow_calcul.domain.models import DonneeHorsBareme, FaitsRisque


def faits(**surcharges) -> FaitsRisque:
    """Le seed 1 (dossier sans risque), modifié champ par champ."""
    base = {
        "suspensions": 0,
        "resiliations": 0,
        "crm": Decimal("0.90"),
        "nb_sinistres_responsables_trois_ans": 0,
        "nb_sinistres_trois_ans": 0,
        "anciennete_permis_mois": 91,
        "puissance_fiscale_cv": 5,
    }
    return FaitsRisque(**{**base, **surcharges})


def test_seed_1_accepte_score_0():
    r = evaluer(faits())
    assert (r.version_bareme, r.classe, r.decision, r.score, r.regles) == (
        "bareme-2026.10-v1",
        "acceptable",
        "ACCEPTE",
        0.0,
        (),
    )


def test_seed_4_refuse_par_la_suspension_seule():  # CRM 1,25 et 2 responsables ne déclenchent pas
    r = evaluer(
        faits(
            suspensions=1,
            crm=Decimal("1.25"),
            nb_sinistres_responsables_trois_ans=2,
            nb_sinistres_trois_ans=2,
            anciennete_permis_mois=70,
        )
    )
    assert [x.regle_id for x in r.regles] == ["R01_SUSPENSION"]
    assert (r.classe, r.decision, r.score) == ("refus", "REFUSE", 1.0)


def test_seed_6_refuse_par_deux_resiliations():
    assert [x.regle_id for x in evaluer(faits(resiliations=2)).regles] == ["R02_RESILIATIONS"]


def test_une_resiliation_ne_suffit_pas():  # seed 2
    r = evaluer(
        faits(resiliations=1, nb_sinistres_trois_ans=1, nb_sinistres_responsables_trois_ans=1)
    )
    assert r.decision == "ACCEPTE"


@pytest.mark.parametrize(
    "surcharge, regle, declenchee",
    [
        ({"crm": Decimal("1.25")}, "R03_CRM", False),
        ({"crm": Decimal("1.26")}, "R03_CRM", True),
        (
            {"nb_sinistres_responsables_trois_ans": 2, "nb_sinistres_trois_ans": 2},
            "R04_SINISTRES_RESPONSABLES",
            False,
        ),
        (
            {"nb_sinistres_responsables_trois_ans": 3, "nb_sinistres_trois_ans": 3},
            "R04_SINISTRES_RESPONSABLES",
            True,
        ),
        ({"nb_sinistres_trois_ans": 4}, "R05_SINISTRES_TOTAL", False),
        ({"nb_sinistres_trois_ans": 5}, "R05_SINISTRES_TOTAL", True),
        (
            {"anciennete_permis_mois": 35, "puissance_fiscale_cv": 7},
            "R06_JEUNE_PERMIS_PUISSANCE",
            False,
        ),
        (
            {"anciennete_permis_mois": 35, "puissance_fiscale_cv": 8},
            "R06_JEUNE_PERMIS_PUISSANCE",
            True,
        ),
        (
            {"anciennete_permis_mois": 36, "puissance_fiscale_cv": 8},
            "R06_JEUNE_PERMIS_PUISSANCE",
            False,
        ),
    ],
)
def test_bornes(surcharge, regle, declenchee):
    ids = [x.regle_id for x in evaluer(faits(**surcharge)).regles]
    assert (regle in ids) == declenchee


def test_toutes_les_regles_declenchees_dans_l_ordre():
    r = evaluer(
        faits(
            suspensions=1,
            resiliations=2,
            crm=Decimal("1.5"),
            nb_sinistres_responsables_trois_ans=3,
            nb_sinistres_trois_ans=5,
            anciennete_permis_mois=10,
            puissance_fiscale_cv=9,
        )
    )
    assert [x.regle_id for x in r.regles] == [
        "R01_SUSPENSION",
        "R02_RESILIATIONS",
        "R03_CRM",
        "R04_SINISTRES_RESPONSABLES",
        "R05_SINISTRES_TOTAL",
        "R06_JEUNE_PERMIS_PUISSANCE",
    ]
    assert r.score == 6.0


@pytest.mark.parametrize("champ", [f.name for f in dataclasses.fields(FaitsRisque)])
def test_donnee_absente_leve_donnee_hors_bareme(champ):
    with pytest.raises(DonneeHorsBareme) as exc:
        evaluer(faits(**{champ: None}))
    assert exc.value.champ == champ


def test_motif_sans_valeur_du_dossier():
    motif = evaluer(faits(crm=Decimal("1.37"))).regles[0].motif
    assert motif == "Le coefficient bonus-malus dépasse 1,25."


@pytest.mark.parametrize("crm", ["0.49", "3.51", "0", "-1"])
def test_crm_hors_bornes_legales_refuse(crm):
    with pytest.raises(DonneeHorsBareme) as exc:
        evaluer(faits(crm=Decimal(crm)))
    assert exc.value.champ == "crm"


@pytest.mark.parametrize("crm", ["0.50", "3.50"])
def test_crm_bornes_legales_incluses(crm):
    evaluer(faits(crm=Decimal(crm)))


def test_profil_dossier_10_classe_refus():
    """Dossier 10 du seed (gestionnaire A, démo K1) : profil du dossier 4, une suspension → R01."""
    r = evaluer(
        faits(
            suspensions=1,
            crm=Decimal("1.25"),
            nb_sinistres_responsables_trois_ans=1,
            nb_sinistres_trois_ans=2,
            anciennete_permis_mois=70,
        )
    )
    regles = [g.regle_id for g in r.regles]
    assert (r.classe, r.decision, regles) == ("refus", "REFUSE", ["R01_SUSPENSION"])


def test_table_regles_ordre_et_seuils():
    assert [r.regle_id for r in REGLES] == [
        "R01_SUSPENSION",
        "R02_RESILIATIONS",
        "R03_CRM",
        "R04_SINISTRES_RESPONSABLES",
        "R05_SINISTRES_TOTAL",
        "R06_JEUNE_PERMIS_PUISSANCE",
    ]
    assert REGLES[2].conditions == (Condition("crm", ">", Decimal("1.25")),)
    assert REGLES[5].conditions == (
        Condition("anciennete_permis_mois", "<", Decimal(36)),
        Condition("puissance_fiscale_cv", ">", Decimal(7)),
    )
    assert {r.effet for r in REGLES} == {"REFUSE"}


def test_chaque_champ_de_condition_existe_dans_les_faits():
    champs = {f.name for f in dataclasses.fields(FaitsRisque)}
    assert {c.champ for r in REGLES for c in r.conditions} <= champs


def test_motif_rendu_est_celui_de_la_table():
    r = evaluer(faits(suspensions=1))
    motif = "Le relevé d'information mentionne une suspension de permis."
    assert r.regles[0].motif == REGLES[0].motif == motif
