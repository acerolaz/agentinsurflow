"""TU — plan de référence et préconditions GO2 (fonctions pures)."""

from dataclasses import replace

import pytest

from agentinsurflow_cluster.domain.models import EtatDossier, Fiche, Pieces, Prime, Risque
from agentinsurflow_cluster.domain.plan import precondition, prochaine_etape

BLOQUE = "garde_fou:entree:prompt_injection"
COMPLET = Pieces("complet", (), "")
INCOMPLET = Pieces("incomplet", ("permis",), "")
PRIME = Prime("600", "50", "v1", "")


def _risque(classe: str) -> Risque:
    return Risque(10, classe, (), "b1", "")


def _fiche(decision: str) -> Fiche:
    return Fiche(decision, "tiers", 1.0, "b1", (), (), ())


def _etat(**kw) -> EtatDossier:
    return EtatDossier("C1", dossier={}, **kw)


def test_pieces_vide():
    assert prochaine_etape(_etat()) == ("appeler_pieces", None)


def test_pieces_incompletes_revue():
    assert prochaine_etape(_etat(pieces=INCOMPLET)) == (
        "orienter_revue_humaine",
        "pieces_incompletes",
    )


def test_pieces_completes_risque_vide():
    assert prochaine_etape(_etat(pieces=COMPLET)) == ("appeler_analyste_risque", None)


def test_classe_limite():
    e = _etat(pieces=COMPLET, risque=_risque("limite"))
    assert prochaine_etape(e) == ("orienter_revue_humaine", "limite")


def test_risque_rempli_fiche_vide():
    e = _etat(pieces=COMPLET, risque=_risque("acceptable"))
    assert prochaine_etape(e) == ("appeler_redacteur", None)


def test_repli_redacteur_cause_posee():
    e = _etat(pieces=COMPLET, risque=_risque("acceptable"), cause="not_found")
    assert prochaine_etape(e) == ("orienter_revue_humaine", "not_found")


def test_accepte_sans_prime():
    e = _etat(pieces=COMPLET, risque=_risque("acceptable"), fiche=_fiche("ACCEPTE"))
    assert prochaine_etape(e) == ("appeler_actuaire", None)


def test_refus_proposer():
    e = _etat(pieces=COMPLET, risque=_risque("refus"), fiche=_fiche("REFUSE"))
    assert prochaine_etape(e) == ("proposer_au_gestionnaire", None)


def test_accepte_avec_prime_proposer():
    e = _etat(pieces=COMPLET, risque=_risque("acceptable"), fiche=_fiche("ACCEPTE"), prime=PRIME)
    assert prochaine_etape(e) == ("proposer_au_gestionnaire", None)


def test_entree_bloquee_risque_rempli():
    e = _etat(pieces=COMPLET, risque=_risque("acceptable"), entree_bloquee=BLOQUE)
    assert prochaine_etape(e) == ("orienter_revue_humaine", BLOQUE)


@pytest.mark.parametrize("pieces", [COMPLET, INCOMPLET])
def test_r2_entree_bloquee_enchaine_pieces_puis_risque_puis_revue(pieces):
    e = _etat(entree_bloquee=BLOQUE)
    assert prochaine_etape(e) == ("appeler_pieces", None)
    e = replace(e, pieces=pieces)
    assert prochaine_etape(e) == ("appeler_analyste_risque", None)
    assert precondition("appeler_analyste_risque", e) is None
    e = replace(e, risque=_risque("acceptable"))
    assert prochaine_etape(e) == ("orienter_revue_humaine", BLOQUE)


def test_r2_precondition_levee_seulement_si_entree_bloquee():
    e = _etat(pieces=INCOMPLET)
    assert precondition("appeler_analyste_risque", e) == "pièces incomplètes"
    assert precondition("appeler_analyste_risque", replace(e, entree_bloquee=BLOQUE)) is None
    # les pièces doivent quand même être remplies
    assert precondition("appeler_analyste_risque", _etat(entree_bloquee=BLOQUE)) is not None


def test_preconditions_table():
    assert precondition("appeler_pieces", _etat()) is None
    assert precondition("appeler_pieces", EtatDossier("C1")) == "dossier non chargé"
    assert precondition("appeler_pieces", _etat(pieces=COMPLET)) == "déjà fait"
    ok = _etat(pieces=COMPLET)
    assert precondition("appeler_analyste_risque", ok) is None
    assert precondition("appeler_analyste_risque", replace(ok, risque=_risque("refus"))) is not None
    avec_risque = replace(ok, risque=_risque("acceptable"))
    assert precondition("appeler_redacteur", avec_risque) is None
    limite = replace(ok, risque=_risque("limite"))
    assert precondition("appeler_redacteur", limite) == "classe limite"
    accepte = replace(avec_risque, fiche=_fiche("ACCEPTE"))
    assert precondition("appeler_actuaire", accepte) is None
    assert precondition("appeler_actuaire", avec_risque) == "pas de prime sans ACCEPTE"
    refuse = replace(avec_risque, fiche=_fiche("REFUSE"))
    assert precondition("appeler_actuaire", refuse) == "pas de prime sans ACCEPTE"
    assert precondition("proposer_au_gestionnaire", refuse) is None
    assert precondition("proposer_au_gestionnaire", accepte) == "fiche ou prime absente"
    assert precondition("proposer_au_gestionnaire", replace(accepte, prime=PRIME)) is None
    assert precondition("orienter_revue_humaine", _etat()) is None


def _simuler(etat: EtatDossier, pieces, classe, decision) -> list[str]:
    """Simule chaque agent avec une sortie donnée ; renvoie la suite d'appels."""
    suite: list[str] = []
    while len(suite) < 10:
        appel, cause = prochaine_etape(etat)
        suite.append(appel)
        if appel != "orienter_revue_humaine":
            assert precondition(appel, etat) is None
        if appel in ("orienter_revue_humaine", "proposer_au_gestionnaire"):
            return suite
        if appel == "appeler_pieces":
            etat = replace(etat, pieces=pieces)
        elif appel == "appeler_analyste_risque":
            etat = replace(etat, risque=_risque(classe))
        elif appel == "appeler_redacteur":
            etat = replace(etat, fiche=_fiche(decision))
        else:
            etat = replace(etat, prime=PRIME)
    return suite


DEPARTS = {
    "vide": _etat(),
    "pieces": _etat(pieces=COMPLET),
    "risque": _etat(pieces=COMPLET, risque=_risque("acceptable")),
    "cause": _etat(cause="not_found"),
    "bloque": _etat(entree_bloquee=BLOQUE),
}


@pytest.mark.parametrize("depart", DEPARTS)
@pytest.mark.parametrize("pieces", [COMPLET, INCOMPLET])
@pytest.mark.parametrize(
    "classe,decision",
    [
        ("acceptable", "ACCEPTE"),
        ("refus", "REFUSE"),
        ("limite", "ACCEPTE"),
        ("acceptable", "REVUE_HUMAINE"),
    ],
)
def test_terminaison_en_5_etapes(depart, pieces, classe, decision):
    suite = _simuler(DEPARTS[depart], pieces, classe, decision)
    assert suite[-1] in ("orienter_revue_humaine", "proposer_au_gestionnaire")
    assert len(suite) <= 5


def test_fiche_revue_humaine():
    e = _etat(pieces=COMPLET, risque=_risque("acceptable"), fiche=_fiche("REVUE_HUMAINE"))
    assert prochaine_etape(e) == ("orienter_revue_humaine", "fiche_revue_humaine")


@pytest.mark.parametrize(
    "extra",
    [
        {},
        {"pieces": COMPLET},
        {"pieces": INCOMPLET, "entree_bloquee": BLOQUE},
        {"pieces": COMPLET, "risque": _risque("limite")},
        {"pieces": COMPLET, "risque": _risque("acceptable"), "entree_bloquee": BLOQUE},
    ],
)
def test_cause_posee_prioritaire(extra):
    assert prochaine_etape(_etat(cause="not_found", **extra)) == (
        "orienter_revue_humaine",
        "not_found",
    )


def test_messages_precondition():
    base = _etat(pieces=COMPLET)
    assert (
        precondition("appeler_analyste_risque", replace(base, risque=_risque("acceptable")))
        == "déjà fait"
    )
    assert precondition("appeler_analyste_risque", _etat(pieces=INCOMPLET)) == "pièces incomplètes"
    assert precondition("appeler_redacteur", base) == "risque absent"
    ok = replace(base, risque=_risque("acceptable"))
    assert precondition("appeler_redacteur", replace(ok, fiche=_fiche("REFUSE"))) == "déjà fait"
    assert (
        precondition("appeler_redacteur", replace(base, risque=_risque("limite")))
        == "classe limite"
    )
