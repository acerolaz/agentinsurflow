"""TU — références : complétude des pièces, risque, prime (fonctions pures)."""

from datetime import date

from agentinsurflow_cluster.domain.models import Pieces, Prime, Risque
from agentinsurflow_cluster.domain.references import prime_de, risque_de, verifier_completude

EXIGEES = {
    "tiers": ("permis", "releve_information"),
    "tous_risques": ("permis", "releve_information", "carte_grise"),
}
EFFET = date(2026, 11, 1)


def _p(type_: str, emission: str = "2026-09-01") -> dict:
    return {"type": type_, "date_emission": emission}


def test_releve_de_4_mois_est_incomplet() -> None:
    res = verifier_completude(
        "tiers", [_p("permis"), _p("releve_information", "2026-06-30")], EFFET, EXIGEES
    )
    assert res.statut == "incomplet"
    assert res.manquantes == ("releve_information",)
    assert "releve_information" in res.note


def test_tout_present_est_complet() -> None:
    res = verifier_completude(
        "tiers", [_p("permis"), _p("releve_information", "2026-08-01")], EFFET, EXIGEES
    )
    assert res == Pieces(statut="complet", manquantes=(), note=res.note)


def test_piece_absente_est_manquante() -> None:
    res = verifier_completude(
        "tous_risques", [_p("permis"), _p("releve_information")], EFFET, EXIGEES
    )
    assert res.manquantes == ("carte_grise",)


def test_risque_de() -> None:
    res = risque_de(
        {
            "classe": "refus",
            "score": 2,
            "regles": [{"regle_id": "R01_SUSPENSION"}, {"regle_id": "R03_CRM"}],
            "version_bareme": "bareme-2026.10-v1",
            "decision": "REFUSE",
        }
    )
    assert res == Risque(2, "refus", ("R01_SUSPENSION", "R03_CRM"), "bareme-2026.10-v1", "")


def test_prime_de() -> None:
    res = prime_de(
        {
            "version_formule": "tarif-v1",
            "prime_ttc_annuelle": "600.00",
            "prime_mensuelle": "50.00",
            "prime_ht": "550.00",
        }
    )
    assert res == Prime("600.00", "50.00", "tarif-v1", "")


def test_plusieurs_releves_le_plus_recent_fait_foi() -> None:
    recent, ancien = _p("releve_information", "2026-08-01"), _p("releve_information", "2026-01-01")
    for ordre in ([recent, ancien], [ancien, recent]):
        res = verifier_completude("tiers", [_p("permis"), *ordre], EFFET, EXIGEES)
        assert res.statut == "complet"


def test_limite_fin_de_mois() -> None:
    # effet 31 mai -> limite 28 février (2026) : le 28/02 passe, le 27/02 non
    for emission, statut in (("2026-02-28", "complet"), ("2026-02-27", "incomplet")):
        res = verifier_completude(
            "tiers", [_p("permis"), _p("releve_information", emission)], date(2026, 5, 31), EXIGEES
        )
        assert res.statut == statut
