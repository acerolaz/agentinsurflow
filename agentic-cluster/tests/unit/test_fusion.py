"""TU — fusion des rapports (D89) et spécifications des agents."""

from dataclasses import replace

import pytest

from agentinsurflow_cluster.domain.fusion import FusionRefusee, fusionner
from agentinsurflow_cluster.domain.models import EtatDossier, Fiche, Pieces, Rapport, Risque
from agentinsurflow_cluster.domain.plan import precondition
from agentinsurflow_cluster.domain.specs import SPECS

RISQUE = Risque(10, "acceptable", (), "b1", "")
FICHE = Fiche("ACCEPTE", "tiers", 1.0, "b1", (), (), ())
PIECES = Pieces("complet", (), "")


def _rapport(agent, **section) -> Rapport:
    return Rapport(agent, section, "llm", None, "p1")


def _etat(**kw) -> EtatDossier:
    return EtatDossier("C1", dossier={}, **kw)


def test_fusion_nominale():
    e = fusionner(_etat(), _rapport("analyste", risque=RISQUE))
    assert e.risque == RISQUE


def test_section_non_possedee():
    with pytest.raises(FusionRefusee) as exc:
        fusionner(_etat(), _rapport("actuaire", fiche=FICHE))
    assert exc.value.code == "SECTION_NON_POSSEDEE"


def test_section_orchestrateur_refusee_aux_agents():
    with pytest.raises(FusionRefusee) as exc:
        fusionner(_etat(), _rapport("pieces", dossier={}))
    assert exc.value.code == "SECTION_NON_POSSEDEE"


def test_deuxieme_rapport_analyste():
    e = fusionner(_etat(), _rapport("analyste", risque=RISQUE))
    with pytest.raises(FusionRefusee) as exc:
        fusionner(e, _rapport("analyste", risque=RISQUE))
    assert exc.value.code == "DEJA_REMPLIE"


def test_type_invalide():
    with pytest.raises(FusionRefusee) as exc:
        fusionner(_etat(), _rapport("analyste", risque={"score": 1}))
    assert exc.value.code == "TYPE_INVALIDE"


def test_rapport_atomique():
    with pytest.raises(FusionRefusee):
        fusionner(_etat(), _rapport("redacteur", sources=(), fiche="x"))


def test_pieces_reecrivable_a_partir_de_la_tentative_2():
    e = fusionner(_etat(), _rapport("pieces", pieces=PIECES))
    with pytest.raises(FusionRefusee):
        fusionner(e, _rapport("pieces", pieces=PIECES))
    neuf = Pieces("incomplet", ("permis",), "")
    assert fusionner(replace(e, tentative=2), _rapport("pieces", pieces=neuf)).pieces == neuf


def test_redacteur_repli_pose_la_cause():
    r = Rapport("redacteur", {}, "repli", "not_found", "p1")
    assert fusionner(_etat(), r).cause == "not_found"


def test_precondition_actuaire_sans_fiche():
    assert precondition("appeler_actuaire", _etat()) == "pas de prime sans ACCEPTE"


def test_specs():
    assert SPECS["redacteur"].delai_s == 8 and SPECS["redacteur"].tours_max == 5
    assert {s.section for s in SPECS.values()} == {"pieces", "risque", "fiche", "prime"}
    assert SPECS["actuaire"].outils_mcp == {"calculer_prime"}
