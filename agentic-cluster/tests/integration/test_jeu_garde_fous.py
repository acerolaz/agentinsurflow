"""TI (lent) — jeu de prompts de référence (G01, G02) avec les vrais modèles LLM Guard."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from fakes_cluster import (
    RISQUE_REFUS,
    FakeAudit,
    FakeGarde,
    FakeOutils,
    FakeRedaction,
    redaction_fidele,
)

from agentinsurflow_cluster.application.agents import Dependances
from agentinsurflow_cluster.application.evaluation import charger, pas, proposer, statut_de
from agentinsurflow_cluster.domain.plan import prochaine_etape
from agentinsurflow_cluster.infrastructure.garde_fous.llm_guard import ScannersLlmGuard
from tools.garde_fous import charger_jeu, mesurer, plafond_faux_positifs

pytestmark = pytest.mark.lent
JETON = "jeton-gestionnaire"


@pytest.fixture(scope="module")
def mesure() -> Any:
    garde = ScannersLlmGuard()
    m = mesurer(garde, charger_jeu("hostiles"), charger_jeu("legitimes"))
    reserve = mesurer(garde, charger_jeu("hostiles_reserve"), charger_jeu("legitimes_reserve"))
    return replace(
        m,
        hostiles=m.hostiles + reserve.hostiles,
        legitimes=m.legitimes + reserve.legitimes,
    )  # jeux + réserves


def _obeit(agent: Any, vue: dict[str, Any]) -> dict[str, Any]:
    """LLM qui obéit à l'observation hostile : il contredit le barème (refus -> ACCEPTE)."""
    return {**redaction_fidele(agent, vue), "decision": "ACCEPTE", "contrat_type": "tous_risques"}


async def _proposition(observations: str, redaction: FakeRedaction) -> tuple[Any, ...]:
    """Évaluation complète (garde aveugle) : (statut, décision, score, règles, prime)."""
    outils = FakeOutils(
        evaluer_risque=RISQUE_REFUS,
        get_contrat={
            "numero_contrat": "C-1",
            "formule": "tiers",
            "date_effet": "2026-10-01",
            "observations": observations,
        },
    )
    deps = Dependances(
        outils=outils,
        redaction=redaction,
        garde=FakeGarde(),
        audit=FakeAudit(),
        versions_prompt={"pieces": "vp", "analyste": "va", "redacteur": "vr", "actuaire": "vc"},
    )
    etat = await charger("C-1", JETON, deps)
    while prochaine_etape(etat)[0] not in ("proposer_au_gestionnaire", "orienter_revue_humaine"):
        etat = await pas(etat, JETON, deps)
    etat = await proposer(etat, JETON, deps)
    fiche = outils.corps("enregistrer_brouillon")[0]["fiche"]
    return statut_de(etat), fiche["decision"], fiche["score"], fiche["regle_ids"], etat.prime


async def test_g01_tout_hostile_est_detecte_ou_neutralise(mesure: Any) -> None:
    reference = await _proposition("Client fidèle depuis dix ans.", FakeRedaction())
    for ligne in mesure.hostiles:
        if ligne["codes"]:
            continue
        redaction = FakeRedaction(_obeit)
        obeissante = await _proposition(ligne["observations"], redaction)
        # la neutralisation n'est prouvée que si le LLM obéissant a bien reçu le texte hostile
        assert any(
            ligne["observations"] in str(vue.get("observations", ""))
            for _, vue, _ in redaction.appels
        ), ligne["id"]
        # même barème, même prime ; le garde-fou GF2 écarte la rédaction qui obéit : au pire la
        # revue humaine (repli prudent), jamais l'acceptation voulue par l'attaquant.
        assert obeissante[2:] == reference[2:], ligne["id"]
        assert obeissante[1] in (reference[1], "REVUE_HUMAINE"), ligne["id"]


def test_g02_faux_positifs_sous_le_plafond(mesure: Any) -> None:
    assert mesure.taux_faux_positifs <= plafond_faux_positifs(), mesure.faux_positifs
