"""Prédiction de fréquence du GLM dans la Function : profil, régions, bornes.

Niveau : TU (domaine pur, artefact commité lu en mémoire, aucune I/O réseau).
"""

import math
from decimal import Decimal

import pytest

from agentinsurflow_calcul.domain import formule
from agentinsurflow_calcul.domain.frequence import (
    DonneeHorsModele,
    PredictionFrequence,
    ProfilFrequence,
    charger_modele,
    predire,
    predire_depuis_artefact,
)
from agentinsurflow_calcul.domain.regions import REGION_PAR_DEPARTEMENT

DOM = {"971", "972", "973", "974", "975", "976"}


def _profil(**kw: object) -> ProfilFrequence:
    base: dict[str, object] = {
        "crm": Decimal("0.90"),
        "puissance_fiscale_cv": 5,
        "departement": "75",
    }
    return ProfilFrequence(**{**base, **kw})  # type: ignore[arg-type]


def test_charger_modele_trouve_l_artefact():
    art = charger_modele()
    assert art["version"].startswith("glm-freq-")
    assert charger_modele() is art  # lu une seule fois


def test_predire_egale_la_task_2():
    art = charger_modele()
    p = predire(art, _profil())
    attendu = predire_depuis_artefact(art, 90.0, 5, "R11")
    assert p == PredictionFrequence(art["version"], attendu)


def test_frequence_dom_hors_modele():
    for dep in sorted(DOM):
        with pytest.raises(DonneeHorsModele) as e:
            predire(charger_modele(), _profil(departement=dep))
        assert e.value.champ == "departement"


@pytest.mark.parametrize("champ", ["crm", "puissance_fiscale_cv", "departement"])
def test_champ_absent_hors_modele(champ):
    with pytest.raises(DonneeHorsModele) as e:
        predire(charger_modele(), _profil(**{champ: None}))
    assert e.value.champ == champ


def test_corse_en_r94():
    assert REGION_PAR_DEPARTEMENT["2A"] == REGION_PAR_DEPARTEMENT["2B"] == "R94"


def test_tous_les_departements_metropolitains_ont_une_region():
    metropole = formule._DEPARTEMENTS - DOM
    assert len(metropole) == 96
    assert set(REGION_PAR_DEPARTEMENT) == metropole
    assert set(REGION_PAR_DEPARTEMENT.values()) == set(charger_modele()["region"]["coefs"])


def test_regions_selon_insee_avant_2016():
    # Repères officiels (COG INSEE, anciennes régions) vérifiés un à un
    r = REGION_PAR_DEPARTEMENT
    assert [r[d] for d in ("75", "92", "95")] == ["R11"] * 3
    assert (r["59"], r["62"]) == ("R31", "R31")
    assert (r["69"], r["38"], r["63"]) == ("R82", "R82", "R83")
    assert (r["31"], r["33"], r["13"], r["34"]) == ("R73", "R72", "R93", "R91")
    assert (r["67"], r["54"], r["35"], r["44"]) == ("R42", "R41", "R53", "R52")


def test_bornes_sans_extrapolation():
    art = charger_modele()
    extreme = predire(art, _profil(crm=Decimal("3.50"), puissance_fiscale_cv=40))
    assert math.isfinite(extreme.frequence_annuelle) and extreme.frequence_annuelle > 0
    bm_max, vp_max = art["bonus_malus"]["max"], art["veh_power"]["max"]
    assert extreme.frequence_annuelle == predire_depuis_artefact(art, bm_max, vp_max, "R11")
    bas = predire(art, _profil(crm=Decimal("0.50"), puissance_fiscale_cv=2))
    assert bas.frequence_annuelle == predire_depuis_artefact(
        art, art["bonus_malus"]["min"], art["veh_power"]["min"], "R11"
    )
