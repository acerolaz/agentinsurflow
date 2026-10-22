"""Formule de prime ``calculer`` : grilles ``Decimal``, arrondi au centime à la fin seulement."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from agentinsurflow_calcul.domain.models import (
    DonneeHorsBareme,
    FaitsPrime,
    ResultatPrime,
    verifier_crm,
)

VERSION_FORMULE = "formule-2026.10-v1"

TAUX_TAXE = Decimal("0.18")
_PRIME_BASE = {
    "tiers": Decimal("250"),
    "tiers_etendu": Decimal("400"),
    "tous_risques": Decimal("650"),
}
_K_USAGE = {
    "prive": Decimal("0.95"),
    "prive_trajet": Decimal("1.00"),
    "professionnel": Decimal("1.35"),
}
_ZONE_URBAINE = {"75", "92", "93", "94", "13"}
_ZONE_RURALE = {"15", "48", "23"}
_DEPARTEMENTS = (
    {f"{i:02d}" for i in range(1, 96) if i != 20} | {"2A", "2B"} | {str(i) for i in range(971, 977)}
)


def _centime(montant: Decimal) -> Decimal:
    return montant.quantize(Decimal("0.01"), ROUND_HALF_UP)


def _k_permis(mois: int | None) -> Decimal:
    if mois is None or mois < 0:
        raise DonneeHorsBareme("anciennete_permis_mois")
    if mois < 12:
        return Decimal("2.00")
    if mois < 24:
        return Decimal("1.50")
    if mois < 36:
        return Decimal("1.25")
    return Decimal("1.00")


def _k_zone(departement: str | None) -> Decimal:
    if departement is None or departement not in _DEPARTEMENTS:
        raise DonneeHorsBareme("departement")
    if departement in _ZONE_URBAINE:
        return Decimal("1.25")
    if departement in _ZONE_RURALE:
        return Decimal("0.90")
    return Decimal("1.00")


def _k_vehicule(cv: int | None) -> Decimal:
    if cv is None or cv < 1:
        raise DonneeHorsBareme("puissance_fiscale_cv")
    if cv <= 4:
        return Decimal("0.90")
    if cv <= 7:
        return Decimal("1.00")
    if cv <= 10:
        return Decimal("1.30")
    return Decimal("1.60")


def calculer(faits: FaitsPrime) -> ResultatPrime:
    """Prime HT/TTC et mensualité ; donnée absente ou hors grille : ``DonneeHorsBareme``."""
    if faits.formule is None or faits.formule not in _PRIME_BASE:
        raise DonneeHorsBareme("formule")
    base = _PRIME_BASE[faits.formule]
    k_permis = _k_permis(faits.anciennete_permis_mois)
    k_zone = _k_zone(faits.departement)
    k_vehicule = _k_vehicule(faits.puissance_fiscale_cv)
    if faits.type_usage is None or faits.type_usage not in _K_USAGE:
        raise DonneeHorsBareme("type_usage")
    k_usage = _K_USAGE[faits.type_usage]
    crm = verifier_crm(faits.crm)

    ht = base * k_permis * k_zone * k_vehicule * k_usage * crm
    ttc = ht * (1 + TAUX_TAXE)
    prime_ht, prime_ttc = _centime(ht), _centime(ttc)
    return ResultatPrime(
        version_formule=VERSION_FORMULE,
        prime_ht=prime_ht,
        montant_taxes=prime_ttc - prime_ht,
        prime_ttc_annuelle=prime_ttc,
        prime_mensuelle=_centime(ttc / 12),
        coefficients={
            "prime_base": base,
            "k_permis": k_permis,
            "k_zone": k_zone,
            "k_vehicule": k_vehicule,
            "k_usage": k_usage,
            "crm": crm,
            "taux_taxe": TAUX_TAXE,
        },
    )
