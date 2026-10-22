"""Formule ``calculer`` : seeds, grilles, arrondi, données hors barème."""

from __future__ import annotations

from decimal import Decimal

import pytest

from agentinsurflow_calcul.domain.formule import calculer
from agentinsurflow_calcul.domain.models import DonneeHorsBareme, FaitsPrime


def faits(**surcharges) -> FaitsPrime:
    """Le seed 1, modifié champ par champ."""
    base = {
        "formule": "tous_risques",
        "anciennete_permis_mois": 91,
        "departement": "75",
        "puissance_fiscale_cv": 5,
        "type_usage": "prive",
        "crm": Decimal("0.90"),
    }
    return FaitsPrime(**{**base, **surcharges})


def test_seed_1():
    r = calculer(faits())
    assert (
        r.version_formule,
        r.prime_ht,
        r.montant_taxes,
        r.prime_ttc_annuelle,
        r.prime_mensuelle,
    ) == (
        "formule-2026.10-v1",
        Decimal("694.69"),
        Decimal("125.04"),
        Decimal("819.73"),
        Decimal("68.31"),
    )
    assert r.coefficients == {
        "prime_base": Decimal("650"),
        "k_permis": Decimal("1.00"),
        "k_zone": Decimal("1.25"),
        "k_vehicule": Decimal("1.00"),
        "k_usage": Decimal("0.95"),
        "crm": Decimal("0.90"),
        "taux_taxe": Decimal("0.18"),
    }


def test_exemple_des_sources_corrige():
    r = calculer(
        faits(
            anciennete_permis_mois=18,
            puissance_fiscale_cv=6,
            type_usage="prive_trajet",
            crm=Decimal("0.85"),
        )
    )
    assert (r.prime_ht, r.montant_taxes, r.prime_ttc_annuelle, r.prime_mensuelle) == (
        Decimal("1035.94"),
        Decimal("186.47"),
        Decimal("1222.41"),
        Decimal("101.87"),
    )


@pytest.mark.parametrize("mois", [0, 11, 12, 36, 91])
@pytest.mark.parametrize("dep", ["75", "23", "69"])
@pytest.mark.parametrize("cv", [4, 8, 11])
def test_taxes_plus_ht_egale_ttc(mois, dep, cv):
    r = calculer(faits(anciennete_permis_mois=mois, departement=dep, puissance_fiscale_cv=cv))
    assert r.prime_ht + r.montant_taxes == r.prime_ttc_annuelle


def test_demi_centime_arrondi_vers_le_haut():
    # 250 × 1,00 × 1,00 × 1,00 × 0,95 × 0,51 = 121,125 → 121,13
    assert calculer(
        faits(formule="tiers", departement="69", crm=Decimal("0.51"))
    ).prime_ht == Decimal("121.13")


@pytest.mark.parametrize(
    ("formule", "base"),
    [("tiers", "250"), ("tiers_etendu", "400"), ("tous_risques", "650")],
)
def test_prime_base(formule, base):
    assert calculer(faits(formule=formule)).coefficients["prime_base"] == Decimal(base)


@pytest.mark.parametrize(
    ("mois", "k"),
    [(11, "2.00"), (12, "1.50"), (23, "1.50"), (24, "1.25"), (35, "1.25"), (36, "1.00")],
)
def test_k_permis(mois, k):
    assert calculer(faits(anciennete_permis_mois=mois)).coefficients["k_permis"] == Decimal(k)


@pytest.mark.parametrize(
    ("dep", "k"),
    [
        *[(d, "1.25") for d in ("75", "92", "93", "94", "13")],
        *[(d, "0.90") for d in ("15", "48", "23")],
        *[(d, "1.00") for d in ("69", "2A", "2B", "974", "971")],
    ],
)
def test_k_zone(dep, k):
    assert calculer(faits(departement=dep)).coefficients["k_zone"] == Decimal(k)


@pytest.mark.parametrize(
    ("cv", "k"),
    [(4, "0.90"), (5, "1.00"), (7, "1.00"), (8, "1.30"), (10, "1.30"), (11, "1.60")],
)
def test_k_vehicule(cv, k):
    assert calculer(faits(puissance_fiscale_cv=cv)).coefficients["k_vehicule"] == Decimal(k)


@pytest.mark.parametrize(
    ("usage", "k"), [("prive", "0.95"), ("prive_trajet", "1.00"), ("professionnel", "1.35")]
)
def test_k_usage(usage, k):
    assert calculer(faits(type_usage=usage)).coefficients["k_usage"] == Decimal(k)


@pytest.mark.parametrize(
    ("surcharge", "champ"),
    [
        *[({"departement": d}, "departement") for d in ("20", "96", "977", "00", "")],
        ({"formule": "tiers_simple"}, "formule"),
        ({"type_usage": "PROMENADE"}, "type_usage"),
        *[
            ({c: None}, c)
            for c in (
                "formule",
                "anciennete_permis_mois",
                "departement",
                "puissance_fiscale_cv",
                "type_usage",
                "crm",
            )
        ],
    ],
)
def test_donnee_hors_bareme(surcharge, champ):
    with pytest.raises(DonneeHorsBareme) as exc:
        calculer(faits(**surcharge))
    assert exc.value.champ == champ


@pytest.mark.parametrize("crm", ["0.49", "3.51", "0", "-1"])
def test_crm_hors_bornes_legales_refuse(crm):
    with pytest.raises(DonneeHorsBareme) as exc:
        calculer(faits(crm=Decimal(crm)))
    assert exc.value.champ == "crm"


@pytest.mark.parametrize("crm", ["0.50", "3.50"])
def test_crm_bornes_legales_incluses(crm):
    calculer(faits(crm=Decimal(crm)))


@pytest.mark.parametrize(
    ("surcharge", "champ"),
    [
        ({"anciennete_permis_mois": -1}, "anciennete_permis_mois"),
        ({"puissance_fiscale_cv": 0}, "puissance_fiscale_cv"),
    ],
)
def test_gardes_negatives(surcharge, champ):
    with pytest.raises(DonneeHorsBareme) as exc:
        calculer(faits(**surcharge))
    assert exc.value.champ == champ
