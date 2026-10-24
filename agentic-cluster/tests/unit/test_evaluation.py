"""TU — cas d'usage d'évaluation : charger, pas, proposer, enregistrer_revue (ports simulés)."""

from __future__ import annotations

import json
from typing import Any

from fakes_cluster import (
    CONTRAT,
    FakeAudit,
    FakeGarde,
    FakeOutils,
    FakeRedaction,
)

from agentinsurflow_cluster.application.agents import Dependances
from agentinsurflow_cluster.application.evaluation import (
    Revue,
    charger,
    enregistrer_revue,
    pas,
    proposer,
    statut_de,
)
from agentinsurflow_cluster.application.serialisation import etat_depuis_dict, etat_vers_dict
from agentinsurflow_cluster.domain.models import EtatDossier
from agentinsurflow_cluster.domain.plan import prochaine_etape
from agentinsurflow_cluster.domain.ports import ErreurOutil

JETON = "jeton-gestionnaire"


def _deps(outils=None, redaction=None, garde=None, audit=None, **kw: Any) -> Dependances:
    return Dependances(
        outils=outils or FakeOutils(),
        redaction=redaction or FakeRedaction(),
        garde=garde or FakeGarde(),
        audit=audit or FakeAudit(),
        versions_prompt={"pieces": "vp", "analyste": "va", "redacteur": "vr", "actuaire": "vc"},
        **kw,
    )


async def _boucle(etat: EtatDossier, deps: Dependances, ecoule_s: float = 0.0) -> EtatDossier:
    while prochaine_etape(etat)[0] not in ("proposer_au_gestionnaire", "orienter_revue_humaine"):
        etat = await pas(etat, JETON, deps, ecoule_s)
    return etat


async def test_charger_lit_le_contrat_avec_la_saga_et_retire_les_observations() -> None:
    outils = FakeOutils()
    garde = FakeGarde()
    etat = await charger("C-1", JETON, _deps(outils, garde=garde))
    assert outils.appels == [("saga", JETON, "get_contrat")]
    assert etat.observations == CONTRAT["observations"]
    assert etat.dossier is not None and "observations" not in etat.dossier
    assert garde.entrees == [CONTRAT["observations"]] and etat.entree_bloquee is None


async def test_charger_journalise_le_signal_d_injection_sans_bloquer() -> None:
    garde = FakeGarde(signal=0.97)
    audit = FakeAudit()
    etat = await charger("C-1", JETON, _deps(garde=garde, audit=audit))
    assert etat.entree_bloquee is None
    assert audit.signaux == [0.97]
    assert garde.entrees == [CONTRAT["observations"]]


async def test_charger_sans_observations_ne_scanne_pas() -> None:
    garde = FakeGarde()
    outils = FakeOutils(get_contrat={**CONTRAT, "observations": None})
    etat = await charger("C-1", JETON, _deps(outils, garde=garde))
    assert garde.entrees == [] and etat.observations is None and etat.entree_bloquee is None


async def test_dossier_acceptable_brouillon_puis_en_analyse_jamais_accepte() -> None:
    """K4 : le statut ACCEPTE n'est écrit qu'après la revue du gestionnaire."""
    outils = FakeOutils()
    deps = _deps(outils)
    etat = await _boucle(await charger("C-1", JETON, deps), deps)
    etat = await proposer(etat, JETON, deps)
    ordre = [o for _, _, o in outils.appels]
    assert ordre.index("enregistrer_brouillon") < ordre.index("update_statut_dossier")
    assert outils.corps("update_statut_dossier") == [
        {"numero_contrat": "C-1", "statut": "EN_ANALYSE"}
    ]
    brouillon = outils.corps("enregistrer_brouillon")[0]
    assert brouillon["fiche"]["decision"] == "ACCEPTE"
    assert brouillon["fiche"]["regle_ids"] == ["R05_CRM"]
    assert brouillon["prime"] == {
        "prime_ttc": 600.0,
        "periodicite": "annuelle",
        "date_effet": "2026-10-01",
    }
    assert statut_de(etat) == "EN_ANALYSE"
    assert "ACCEPTE" not in [a.get("statut") for a in outils.corps("update_statut_dossier")]


async def test_enregistrer_etat_apres_chaque_fusion_sans_observations() -> None:
    outils = FakeOutils()
    deps = _deps(outils, trace_id=lambda: "ab" * 16)
    etat = await _boucle(await charger("C-1", JETON, deps), deps)
    corps = outils.corps("enregistrer_etat")
    assert len(corps) == 4  # pièces, risque, fiche, prime
    assert all(a["numero_contrat"] == "C-1" for a in corps)
    dernier = corps[-1]["etat"]
    assert set(dernier) == {"statut_parcours", "tentative", "sections", "rapports", "tours"}
    assert {s["section"] for s in dernier["sections"]} == {
        "dossier",
        "pieces",
        "risque",
        "sources",
        "fiche",
        "prime",
    }
    assert [r["agent"] for r in dernier["rapports"]] == [
        "pieces",
        "analyste",
        "redacteur",
        "actuaire",
    ]
    assert dernier["rapports"][0]["trace_id"] == "ab" * 16
    assert dernier["tours"][0] == {
        "tour": 1,
        "outil_appele": "appeler_pieces",
        "precondition": None,
        "mode": "llm",
    }
    assert CONTRAT["observations"] not in json.dumps(corps)  # type: ignore[operator]
    assert {a for a, _, o in outils.appels if o == "enregistrer_etat"} == {"saga"}
    assert etat.fiche is not None


async def test_observations_hostiles_aucune_redaction_revue_humaine_score_present() -> None:
    redaction = FakeRedaction()
    audit = FakeAudit()
    outils = FakeOutils()
    deps = _deps(outils, redaction, FakeGarde(entree=["prompt_injection"]), audit)
    etat = await charger("C-1", JETON, deps)
    assert etat.entree_bloquee == "garde_fou:entree:prompt_injection"
    etat = await _boucle(etat, deps)
    etat = await proposer(etat, JETON, deps)
    assert redaction.appels == []
    assert statut_de(etat) == "REVUE_HUMAINE"
    assert outils.corps("update_statut_dossier") == [
        {"numero_contrat": "C-1", "statut": "REVUE_HUMAINE"}
    ]
    fiche = outils.corps("enregistrer_brouillon")[0]["fiche"]
    assert fiche["decision"] == "REVUE_HUMAINE" and fiche["score"] == 3
    assert fiche["contrat_type"] == "" and fiche["citations"] == []
    assert fiche["motifs"] == ["Contrôle d'entrée : revue humaine requise."]
    assert (
        fiche["regle_ids"] == ["R05_CRM"]
        and "prime" not in outils.corps("enregistrer_brouillon")[0]
    )
    causes = [r.cause for _, r, _, _ in audit.traces]
    assert "garde_fou:entree:prompt_injection" in causes
    assert ["prompt_injection"] in [g for _, _, g, _ in audit.traces]
    assert "prompt_injection" not in json.dumps(fiche)


async def test_revue_humaine_sans_risque_fiche_provisoire_inconnue() -> None:
    outils = FakeOutils(lister_pieces=ErreurOutil("MCP_INDISPONIBLE"))
    deps = _deps(outils)
    etat = await _boucle(await charger("C-1", JETON, deps), deps)
    assert etat.risque is None and etat.cause == "erreur"
    await proposer(etat, JETON, deps)
    fiche = outils.corps("enregistrer_brouillon")[0]["fiche"]
    assert (fiche["score"], fiche["version_bareme"], fiche["regle_ids"]) == (0, "inconnue", [])
    assert fiche["motifs"] == ["Revue humaine requise."]


async def test_garde_globale_duree_orienter_revue_humaine() -> None:
    deps = _deps()
    etat = await charger("C-1", JETON, deps)
    etat = await _boucle(etat, deps, ecoule_s=24.0)  # 25 - 24 - 2 < 0,3 s
    assert etat.cause == "duree" and etat.pieces is None
    assert etat.tours[-1]["outil_appele"] == "appeler_pieces"


async def test_budget_de_l_agent_borne_par_le_reste_du_budget_global() -> None:
    redaction = FakeRedaction()
    budgets: list[float] = []

    async def espion(agent: Any, vue: Any, budget_s: float, jeton: str = "") -> Any:
        budgets.append(budget_s)
        return None

    redaction.rediger = espion  # type: ignore[method-assign]
    deps = _deps(redaction=redaction)
    await pas(await charger("C-1", JETON, deps), JETON, deps, ecoule_s=22.0)  # 25-22-2 = 1 s
    assert budgets == [1.0]


async def test_enregistrer_revue_motif_dans_validation_puis_statut() -> None:
    outils = FakeOutils()
    deps = _deps(outils)
    etat = await proposer(await _boucle(await charger("C-1", JETON, deps), deps), JETON, deps)
    revue = Revue("ACCEPTE", "VALIDEE", "Conforme au barème.")
    etat = await enregistrer_revue(etat, revue, JETON, deps)
    assert etat.validation == {
        "decision": "ACCEPTE",
        "validation": "VALIDEE",
        "motif": "Conforme au barème.",
    }
    derniere = outils.corps("enregistrer_etat")[-1]["etat"]
    assert derniere["statut_parcours"] == "ACCEPTE"
    assert {"section": "validation", "contenu": etat.validation} in derniere["sections"]
    assert outils.corps("update_statut_dossier")[-1] == {
        "numero_contrat": "C-1",
        "statut": "ACCEPTE",
        "validation": "VALIDEE",
    }
    assert [o for _, _, o in outils.appels][-2:] == ["enregistrer_etat", "update_statut_dossier"]


def test_serialisation_aller_retour_conserve_les_tuples() -> None:
    from agentinsurflow_cluster.domain.models import Fiche, Pieces

    etat = EtatDossier(
        "C-1",
        dossier={"a": 1},
        pieces=Pieces("incomplet", ("permis",), "n"),
        fiche=Fiche("REFUSE", "tiers", 12.0, "b", ("R1",), ("m",), ("c",)),
        sources=({"doc_id": "x"},),
        tours=({"tour": 1},),
    )
    brut = json.loads(json.dumps(etat_vers_dict(etat)))  # comme un point de reprise
    assert etat_depuis_dict(brut) == etat


async def test_proposer_sans_date_effet_revue_humaine_cause_erreur() -> None:
    from agentinsurflow_cluster.domain.models import Fiche, Pieces, Prime, Risque

    outils = FakeOutils()
    etat = EtatDossier(
        "C-1",
        dossier={},
        pieces=Pieces("complet", (), "n"),
        risque=Risque(3, "acceptable", (), "b", "n"),
        fiche=Fiche("ACCEPTE", "tiers", 3, "b", (), ("m",), ("c",)),
        prime=Prime("600.00", "50.00", "v", "e"),
    )
    etat = await proposer(etat, JETON, _deps(outils))
    assert statut_de(etat) == "REVUE_HUMAINE"
    assert outils.corps("update_statut_dossier")[0]["statut"] == "REVUE_HUMAINE"
    assert "prime" not in outils.corps("enregistrer_brouillon")[0]


async def test_fiche_acceptee_remplacee_par_la_provisoire_apres_garde_de_duree() -> None:
    outils = FakeOutils()
    deps = _deps(outils)
    etat = await charger("C-1", JETON, deps)
    for _ in range(3):  # pièces, risque, rédacteur : la fiche ACCEPTE existe
        etat = await pas(etat, JETON, deps)
    assert etat.fiche is not None and etat.fiche.decision == "ACCEPTE"
    etat = await pas(etat, JETON, deps, ecoule_s=24.0)  # l'actuaire n'a plus le temps
    assert etat.cause == "duree"
    await proposer(etat, JETON, deps)
    brouillon = outils.corps("enregistrer_brouillon")[0]
    assert brouillon["fiche"]["decision"] == "REVUE_HUMAINE" and "prime" not in brouillon
    assert brouillon["fiche"]["motifs"] == ["Délai d'analyse dépassé : revue humaine requise."]
