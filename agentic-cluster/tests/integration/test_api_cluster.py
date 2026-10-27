"""TI — API complète en mémoire : jeton Entra, graphe LangGraph (MemorySaver), ports factices."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import Any

import httpx
import pytest
from fakes_cluster import (
    CONTRAT,
    REGLAGES,
    FakeAudit,
    FakeGarde,
    FakeOutils,
    FakeRedaction,
    redaction_fidele,
)
from jetons_cluster_de_test import (
    CLIENT_CLUSTER,
    EMETTEUR_V1,
    FauxJwks,
    config_cluster,
    creer,
)
from langgraph.checkpoint.memory import MemorySaver

from agentinsurflow_cluster.api.app import creer_app
from agentinsurflow_cluster.application.agents import Dependances
from agentinsurflow_cluster.domain.ports import ErreurOutil
from agentinsurflow_cluster.infrastructure.langgraph.graphe import ServiceEvaluation
from agentinsurflow_cluster.infrastructure.llm.fabrique import version_prompt

REVUE = {"decision": "ACCEPTE", "validation": "VALIDEE", "motif": "Conforme au barème."}


class Banc:
    def __init__(self, garde: FakeGarde | None = None, outils: FakeOutils | None = None) -> None:
        self.outils = outils or FakeOutils()
        self.redaction = FakeRedaction()
        self.audit = FakeAudit()
        self.deps = Dependances(
            self.outils, self.redaction, garde or FakeGarde(), self.audit, REGLAGES,
            versions_prompt={a: version_prompt(g.prompt) for a, g in REGLAGES.items()},
        )  # fmt: skip

    @asynccontextmanager
    async def composition(self, _cfg: Any) -> AsyncIterator[ServiceEvaluation]:
        self.saver = MemorySaver()
        self.service = ServiceEvaluation(self.deps, self.saver)
        yield self.service


@asynccontextmanager
async def client(banc: Banc, jeton: str | None = None) -> AsyncIterator[httpx.AsyncClient]:
    app = creer_app(banc.composition)
    app.state.config = config_cluster()
    app.state.jwks = FauxJwks()
    entetes = {"Authorization": f"Bearer {jeton or creer()}"}
    async with app.router.lifespan_context(app):
        while app.state.service is None:  # la composition se prépare en tâche de fond
            await asyncio.sleep(0)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", headers=entetes
        ) as c:
            yield c


import asyncio  # noqa: E402


async def test_evaluation_en_analyse_puis_rejeu_409_puis_revue_accepte() -> None:
    banc = Banc()
    async with client(banc) as c:
        r = await c.post("/evaluations/C-1")
        assert r.status_code == 200, r.text
        corps = r.json()
        assert corps["statut"] == "EN_ANALYSE" and corps["message"] is None
        assert corps["fiche"]["decision"] == "ACCEPTE"
        assert corps["prime"]["prime_ttc_annuelle"] == "600.00"
        assert [e["outil_appele"] for e in corps["synthese"]] == [
            "appeler_pieces", "appeler_analyste_risque", "appeler_redacteur", "appeler_actuaire"
        ]  # fmt: skip

        rejeu = await c.post("/evaluations/C-1")
        assert rejeu.status_code == 409
        assert rejeu.headers["content-type"].startswith("application/problem+json")
        assert rejeu.json()["code"] == "EVALUATION_EN_ATTENTE"

        revue = await c.post("/evaluations/C-1/revue", json=REVUE)
        assert revue.status_code == 200 and revue.json() == {"statut": "ACCEPTE"}
        statuts = [a["statut"] for a in banc.outils.corps("update_statut_dossier")]
        assert statuts == ["EN_ANALYSE", "ACCEPTE"]

        sans_attente = await c.post("/evaluations/C-1/revue", json=REVUE)
        assert sans_attente.status_code == 409
        assert sans_attente.json()["code"] == "AUCUNE_REVUE_EN_ATTENTE"


async def test_le_jeton_du_gestionnaire_descend_aux_agents_sans_entrer_dans_l_etat() -> None:
    banc = Banc()
    jeton = creer()
    async with client(banc, jeton) as c:
        await c.post("/evaluations/C-1")
    assert {j for _, j, _ in banc.outils.appels} == {jeton}
    assert jeton not in json.dumps(banc.outils.arguments)


async def test_le_jeton_n_est_ecrit_dans_aucun_point_de_reprise() -> None:
    banc = Banc()
    jeton = creer()
    async with client(banc, jeton) as c:
        await c.post("/evaluations/C-1")
    ecrit = repr(banc.saver.storage) + repr(banc.saver.blobs) + repr(banc.saver.writes)
    assert jeton not in ecrit and "pieces" in ecrit


OBSERVATION = "Observation confidentielle ZX42 du gestionnaire."


def _octets(valeur: Any) -> bytes:
    """Tout le contenu binaire ou textuel d'une structure de points de reprise, à plat."""
    if isinstance(valeur, bytes | bytearray):
        return bytes(valeur)
    if isinstance(valeur, str):
        return valeur.encode()
    if isinstance(valeur, dict):
        return b"".join(_octets(k) + _octets(v) for k, v in valeur.items())
    if isinstance(valeur, list | tuple | set):
        return b"".join(_octets(v) for v in valeur)
    return b""


async def test_observations_jamais_dans_un_point_de_reprise_mais_recues_par_le_redacteur() -> None:
    banc = Banc(outils=FakeOutils(get_contrat={**CONTRAT, "observations": OBSERVATION}))
    async with client(banc) as c:
        assert (await c.post("/evaluations/C-1")).status_code == 200
    stockage = _octets(banc.saver.storage) + _octets(banc.saver.blobs) + _octets(banc.saver.writes)
    assert b"pieces" in stockage and OBSERVATION.encode() not in stockage
    redacteur = [vue for agent, vue, _ in banc.redaction.appels if agent == "redacteur"]
    assert OBSERVATION in redacteur[0]["observations"]
    assert OBSERVATION not in json.dumps(banc.outils.arguments)


class SortiePanne(FakeOutils):
    """Échoue une fois à l'écriture du statut ACCEPTE (reprise sur panne du MCP)."""

    def __init__(self) -> None:
        super().__init__()
        self.echecs = 0

    async def appeler(self, agent: str, jeton: str, outil: str, arguments: dict[str, Any]) -> Any:
        if outil == "update_statut_dossier" and arguments["statut"] == "ACCEPTE":
            if self.echecs == 0:
                self.echecs += 1
                raise ErreurOutil("MCP_INDISPONIBLE")
        return await super().appeler(agent, jeton, outil, arguments)


async def test_revue_non_perdue_si_l_enregistrement_echoue_puis_rejoue() -> None:
    outils = SortiePanne()
    banc = Banc(outils=outils)
    async with client(banc) as c:
        await c.post("/evaluations/C-1")
        premiere = await c.post("/evaluations/C-1/revue", json=REVUE)
        assert premiere.status_code == 502
        assert (await c.post("/evaluations/C-1")).status_code == 409  # la revue attend encore
        seconde = await c.post("/evaluations/C-1/revue", json=REVUE)
        assert seconde.status_code == 200 and seconde.json() == {"statut": "ACCEPTE"}
    ecrits = [a for a in outils.corps("update_statut_dossier") if a["statut"] == "ACCEPTE"]
    assert len(ecrits) == 1


async def test_statut_fige_de_l_admin_devient_409_dossier_decide_sur_les_deux_routes() -> None:
    outils = FakeOutils(update_statut_dossier=ErreurOutil("STATUT_FIGE"))
    async with client(Banc(outils=outils)) as c:
        r = await c.post("/evaluations/C-1")
        assert r.status_code == 409 and r.json()["code"] == "DOSSIER_DECIDE"
    outils = FakeOutils()
    async with client(Banc(outils=outils)) as c:
        await c.post("/evaluations/C-1")
        outils.reponses["update_statut_dossier"] = ErreurOutil("STATUT_FIGE")
        r = await c.post("/evaluations/C-1/revue", json=REVUE)
    assert r.status_code == 409 and r.json()["code"] == "DOSSIER_DECIDE"


def _jeton_de(oid: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {creer(oid=oid)}"}


def _points_de_reprise(banc: Banc) -> str:
    s = banc.saver
    return repr(s.storage) + repr(s.blobs) + repr(s.writes)


async def test_bola_un_autre_gestionnaire_ne_voit_ni_ne_reprend_le_dossier_en_pause() -> None:
    banc = Banc()
    async with client(banc) as c:
        assert (await c.post("/evaluations/C-1")).status_code == 200  # A : en pause
        avant = _points_de_reprise(banc)
        b = _jeton_de("oid-gestionnaire-b")
        evaluer = await c.post("/evaluations/C-1", headers=b)
        reviser = await c.post("/evaluations/C-1/revue", json=REVUE, headers=b)
        assert _points_de_reprise(banc) == avant  # le point de reprise de A est intact
        for r in (evaluer, reviser):
            assert r.status_code == 404 and r.json()["code"] == "CONTRAT_INTROUVABLE"
        ok = await c.post("/evaluations/C-1/revue", json=REVUE)  # A reprend toujours
        assert ok.status_code == 200 and ok.json() == {"statut": "ACCEPTE"}
        # dossier décidé : B reçoit encore 404 (jamais 409, qui révélerait l'existence)
        for r in (
            await c.post("/evaluations/C-1", headers=b),
            await c.post("/evaluations/C-1/revue", json=REVUE, headers=b),
        ):
            assert r.status_code == 404
    assert [a["statut"] for a in banc.outils.corps("update_statut_dossier")] == [
        "EN_ANALYSE", "ACCEPTE"
    ]  # fmt: skip


async def test_tentative_incrementee_a_chaque_evaluation_et_trace_id_jamais_vide() -> None:
    banc = Banc(garde=FakeGarde(entree=["prompt_injection"]))  # REVUE_HUMAINE : on peut réévaluer
    async with client(banc) as c:
        await c.post("/evaluations/C-1")
        premiere = len(banc.outils.corps("enregistrer_etat"))
        assert (await c.post("/evaluations/C-1")).status_code == 200
    etats = [a["etat"] for a in banc.outils.corps("enregistrer_etat")]
    assert {e["tentative"] for e in etats[:premiere]} == {1}
    seconde = etats[premiere:]
    assert {e["tentative"] for e in seconde} == {2}
    assert seconde[-1]["tours"] and seconde[-1]["tours"][0]["tour"] == 1  # tours de la 2e conservés
    rapports = [r for e in etats for r in e["rapports"]]
    assert rapports and all(r["trace_id"] for r in rapports)


class OutilsLents(FakeOutils):
    """Un MCP factice qui ne répond pas dans les temps pour l'un de ses outils."""

    def __init__(self, lent: str) -> None:
        super().__init__()
        self.lent = lent

    async def appeler(self, agent: str, jeton: str, outil: str, arguments: dict[str, Any]) -> Any:
        if outil == self.lent:
            await asyncio.sleep(30)
        return await super().appeler(agent, jeton, outil, arguments)


def _banc_presse(lent: str) -> Banc:
    banc = Banc(outils=OutilsLents(lent))
    banc.deps = replace(banc.deps, budget_global_s=1.0, reserve_s=0.2)
    return banc


async def test_budget_depasse_dans_un_agent_revue_humaine_cause_duree() -> None:
    banc = _banc_presse("lister_pieces")
    debut = time.monotonic()
    async with client(banc) as c:
        r = await c.post("/evaluations/C-1")
    assert time.monotonic() - debut < 6
    corps = r.json()
    assert r.status_code == 200 and corps["statut"] == "REVUE_HUMAINE"
    assert corps["message"] == "Ce dossier nécessite une revue humaine." and "duree" not in r.text
    assert [a["statut"] for a in banc.outils.corps("update_statut_dossier")] == ["REVUE_HUMAINE"]
    assert banc.outils.corps("enregistrer_brouillon")  # la fiche provisoire est écrite


async def test_budget_depasse_avant_tout_etat_503_delai_depasse() -> None:
    banc = _banc_presse("get_contrat")
    async with client(banc) as c:
        r = await c.post("/evaluations/C-1")
    assert r.status_code == 503 and r.json()["code"] == "DELAI_DEPASSE"
    assert r.headers["content-type"].startswith("application/problem+json")
    assert banc.outils.corps("update_statut_dossier") == []


async def test_motif_avec_donnee_personnelle_422_sans_reprendre_la_revue() -> None:
    banc = Banc()
    async with client(banc) as c:
        await c.post("/evaluations/C-1")
        avant = _points_de_reprise(banc)
        r = await c.post(
            "/evaluations/C-1/revue", json={**REVUE, "motif": "Voir jean.dupont@exemple.fr"}
        )
        assert r.status_code == 422 and r.json()["code"] == "REQUETE_INVALIDE"
        assert r.json()["champs"] == ["motif"] and "dupont" not in r.text
        assert _points_de_reprise(banc) == avant
        assert (await c.post("/evaluations/C-1/revue", json=REVUE)).status_code == 200


async def test_deux_evaluations_concurrentes_un_seul_brouillon() -> None:
    banc = Banc()
    async with client(banc) as c:
        a, b = await asyncio.gather(c.post("/evaluations/C-1"), c.post("/evaluations/C-1"))
    assert sorted([a.status_code, b.status_code]) == [200, 409]
    assert len(banc.outils.corps("enregistrer_brouillon")) == 1


async def test_evaluation_d_un_dossier_decide_409_dossier_decide() -> None:
    async with client(Banc()) as c:
        await c.post("/evaluations/C-1")
        await c.post("/evaluations/C-1/revue", json={**REVUE, "decision": "REFUSE"})
        r = await c.post("/evaluations/C-1")
    assert r.status_code == 409 and r.json()["code"] == "DOSSIER_DECIDE"
    assert r.headers["content-type"].startswith("application/problem+json")


async def test_synthese_ne_porte_que_le_tour_et_l_outil() -> None:
    banc = Banc(garde=FakeGarde(entree=["prompt_injection"]))
    async with client(banc) as c:
        r = await c.post("/evaluations/C-1")
    assert all(set(e) == {"tour", "outil_appele"} for e in r.json()["synthese"])
    assert "repli" not in r.text and "precondition" not in r.text


async def test_revue_humaine_ne_revele_ni_cause_ni_detecteur() -> None:
    banc = Banc(garde=FakeGarde(entree=["prompt_injection"]))
    async with client(banc) as c:
        r = await c.post("/evaluations/C-1")
    assert r.status_code == 200
    corps = r.json()
    assert corps["statut"] == "REVUE_HUMAINE"
    assert corps["message"] == "Ce dossier nécessite une revue humaine."
    assert corps["fiche"] is None and corps["prime"] is None
    assert "garde_fou" not in r.text and "prompt_injection" not in r.text
    assert banc.redaction.appels == []


async def test_k5_llm_inactif_200_revue_humaine_score_et_message_indisponible() -> None:
    banc = Banc()
    banc.redaction.scenario = lambda agent, vue: None  # INSURFLOW_LLM_ACTIF=false : aucun modèle
    debut = time.monotonic()
    async with client(banc) as c:
        r = await c.post("/evaluations/C-1")
    assert time.monotonic() - debut < 30
    assert r.status_code == 200
    corps = r.json()
    assert corps["statut"] == "REVUE_HUMAINE"
    assert corps["score"] == 3 and corps["message"] == "Service temporairement indisponible"
    assert corps["fiche"] is None and corps["prime"] is None
    assert "llm_ko" not in r.text


async def test_k5_pii_en_sortie_n_est_pas_une_panne_du_llm() -> None:
    banc = Banc()
    banc.redaction.scenario = lambda agent, vue: (
        {"erreur": "garde_fou:pii"} if agent == "redacteur" else redaction_fidele(agent, vue)
    )
    async with client(banc) as c:
        r = await c.post("/evaluations/C-1")
    corps = r.json()
    assert corps["statut"] == "REVUE_HUMAINE" and corps["score"] == 3
    assert corps["message"] == "Ce dossier nécessite une revue humaine."
    assert "pii" not in r.text


async def test_revue_humaine_n_attend_aucune_revue() -> None:
    banc = Banc(garde=FakeGarde(entree=["prompt_injection"]))
    async with client(banc) as c:
        await c.post("/evaluations/C-1")
        r = await c.post("/evaluations/C-1/revue", json=REVUE)
    assert r.status_code == 409


async def test_contrat_introuvable_404_puis_reprise_possible() -> None:
    outils = FakeOutils(get_contrat=ErreurOutil("CONTRAT_INTROUVABLE"))
    banc = Banc(outils=outils)
    async with client(banc) as c:
        r = await c.post("/evaluations/C-9")
        assert r.status_code == 404 and r.json()["code"] == "CONTRAT_INTROUVABLE"
        outils.reponses["get_contrat"] = CONTRAT
        assert (await c.post("/evaluations/C-9")).status_code == 200  # un échec n'attend rien


async def test_bola_la_tentative_d_un_autre_gestionnaire_ne_s_approprie_pas_le_dossier() -> None:
    # B tente le dossier de A avant toute évaluation : le 404 ne doit pas lui laisser le point
    # de reprise (l'entrée {"oid": B} est écrite avant `charger`), sinon A serait bloqué en 404.
    outils = FakeOutils(get_contrat=ErreurOutil("CONTRAT_INTROUVABLE"))
    banc = Banc(outils=outils)
    async with client(banc) as c:
        r = await c.post("/evaluations/C-7", headers=_jeton_de("oid-gestionnaire-b"))
        assert r.status_code == 404 and r.json()["code"] == "CONTRAT_INTROUVABLE"
        outils.reponses["get_contrat"] = CONTRAT  # A, propriétaire, est servi par underwriting
        assert (await c.post("/evaluations/C-7")).status_code == 200


async def test_panne_d_outil_502() -> None:
    banc = Banc(outils=FakeOutils(get_contrat=ErreurOutil("MCP_INDISPONIBLE")))
    async with client(banc) as c:
        r = await c.post("/evaluations/C-1")
    assert r.status_code == 502 and r.json()["code"] == "OUTIL_INDISPONIBLE"


def _etats(banc: Banc) -> list[dict[str, Any]]:
    return [a["etat"] for a in banc.outils.corps("enregistrer_etat")]


async def test_pause_avant_evaluation_arrete_apres_le_premier_agent() -> None:
    banc = Banc()
    async with client(banc) as c:
        p = await c.post("/evaluations/C-1/pause")
        r = await c.post("/evaluations/C-1")
    assert p.status_code == 202 and p.json() == {"pause": "demandee"}
    assert r.status_code == 200, r.text
    assert r.json()["statut"] == "EN_PAUSE" and len(r.json()["synthese"]) == 1
    assert _etats(banc)[-1]["statut_parcours"] == "EN_PAUSE"


async def test_reprise_va_au_bout_sans_nouvelle_tentative_et_revoit_les_observations() -> None:
    banc = Banc()
    async with client(banc) as c:
        await c.post("/evaluations/C-1/pause")
        await c.post("/evaluations/C-1")
        r = await c.post("/evaluations/C-1")
    assert r.status_code == 200 and r.json()["statut"] == "EN_ANALYSE", r.text
    assert {e["tentative"] for e in _etats(banc)} == {1}
    redacteur = [vue for agent, vue, _ in banc.redaction.appels if agent == "redacteur"]
    assert CONTRAT["observations"] in redacteur[0]["observations"]


async def test_reprise_apres_longue_pause_ne_depasse_pas_le_budget() -> None:
    maintenant = [0.0]
    banc = Banc()
    banc.deps = replace(banc.deps, horloge=lambda: maintenant[0])
    async with client(banc) as c:
        await c.post("/evaluations/C-1/pause")
        await c.post("/evaluations/C-1")
        maintenant[0] += 3600
        r = await c.post("/evaluations/C-1")
    assert r.json()["statut"] == "EN_ANALYSE", r.text


async def test_revue_pendant_la_pause_409() -> None:
    async with client(Banc()) as c:
        await c.post("/evaluations/C-1/pause")
        await c.post("/evaluations/C-1")
        r = await c.post("/evaluations/C-1/revue", json=REVUE)
    assert r.status_code == 409 and r.json()["code"] == "AUCUNE_REVUE_EN_ATTENTE"


async def test_pause_apres_proposition_oubliee() -> None:
    banc = Banc()
    async with client(banc) as c:
        assert (await c.post("/evaluations/C-1")).json()["statut"] == "EN_ANALYSE"
        await c.post("/evaluations/C-1/pause")
        await c.post("/evaluations/C-1/revue", json={**REVUE, "decision": "REFUSE"})
        r = await c.post("/evaluations/C-1")
    assert r.status_code == 409 and r.json()["code"] == "DOSSIER_DECIDE"
    assert banc.service._pauses == set()


async def test_pause_autre_gestionnaire_404() -> None:
    banc = Banc()
    async with client(banc) as c:
        await c.post("/evaluations/C-1")
        r = await c.post("/evaluations/C-1/pause", headers=_jeton_de("oid-gestionnaire-b"))
    assert r.status_code == 404 and r.json()["code"] == "CONTRAT_INTROUVABLE"
    assert banc.service._pauses == set()


async def test_deux_evaluations_simultanees_la_seconde_409_en_cours() -> None:
    async def lente(agent: str, vue: dict[str, Any], budget_s: float, jeton: str = "") -> Any:
        await asyncio.sleep(0.2)
        return redaction_fidele(agent, vue)  # type: ignore[arg-type]

    banc = Banc()
    banc.redaction.rediger = lente  # type: ignore[method-assign]
    async with client(banc) as c:
        a, b = await asyncio.gather(c.post("/evaluations/C-1"), c.post("/evaluations/C-1"))
    assert sorted([a.status_code, b.status_code]) == [200, 409]
    refus = a if a.status_code == 409 else b
    assert refus.json()["code"] == "EVALUATION_EN_COURS"


async def test_outil_en_429_rend_429_avec_retry_after() -> None:
    banc = Banc(outils=FakeOutils(get_contrat=ErreurOutil("TROP_DE_REQUETES", "17")))
    async with client(banc) as c:
        r = await c.post("/evaluations/C-1")
    assert r.status_code == 429 and r.json()["code"] == "TROP_DE_REQUETES"
    assert r.headers["retry-after"] == "17"


async def test_une_evaluation_complete_tient_deux_fois_dans_les_limites() -> None:
    # Limites de la gateway : Mcp 60/min par oid|azp, Llm 30/min par azp ;
    # deux évaluations par minute doivent passer.
    banc = Banc()
    async with client(banc) as c:
        assert (await c.post("/evaluations/C-1")).status_code == 200
        assert (await c.post("/evaluations/C-1/revue", json=REVUE)).status_code == 200
    saga = sum(1 for agent, _, _ in banc.outils.appels if agent == "saga")
    agents = len(banc.outils.appels) - saga
    assert saga <= 30 and agents <= 30, (saga, agents)
    assert len(banc.redaction.appels) <= 15


@pytest.mark.parametrize("motif", ["", "x" * 501])
async def test_motif_obligatoire_1_a_500_caracteres(motif: str) -> None:
    async with client(Banc()) as c:
        await c.post("/evaluations/C-1")
        r = await c.post("/evaluations/C-1/revue", json={**REVUE, "motif": motif})
    assert r.status_code == 422 and r.json()["code"] == "REQUETE_INVALIDE"
    assert r.json()["champs"] == ["motif"] and "xxx" not in r.text


async def test_jeton_d_audience_mcp_401() -> None:
    async with client(Banc(), creer(aud="api://agentinsurflow-mcp")) as c:
        r = await c.post("/evaluations/C-1")
    assert r.status_code == 401 and r.json()["code"] == "JETON_INVALIDE"
    assert r.headers["content-type"].startswith("application/problem+json")


async def test_sans_jeton_401_et_sans_role_403() -> None:
    banc = Banc()
    async with client(banc) as c:
        c.headers.pop("Authorization")
        assert (await c.post("/evaluations/C-1")).json()["code"] == "JETON_ABSENT"
    async with client(banc, creer(roles=[])) as c:
        r = await c.post("/evaluations/C-1")
    assert r.status_code == 403 and r.json()["code"] == "ROLE_MANQUANT"


@pytest.mark.parametrize(
    ("aud", "iss"),
    [(CLIENT_CLUSTER, EMETTEUR_V1), (f"api://{CLIENT_CLUSTER}", EMETTEUR_V1)],
)
async def test_audience_appid_et_emetteur_v1_acceptes(aud: str, iss: str) -> None:
    async with client(Banc(), creer(aud=aud, iss=iss)) as c:
        assert (await c.post("/evaluations/C-1")).status_code == 200


async def test_health_200_une_fois_les_garde_fous_prets() -> None:
    async with client(Banc()) as c:
        r = await c.get("/health")
    assert r.status_code == 200
    corps = r.json()
    assert corps["garde_fous"] == "prets" and corps["version"] == "dev"
    assert set(corps["prompts"]) == {"pieces", "analyste", "redacteur", "actuaire"}
    assert all(len(v) == 12 for v in corps["prompts"].values())


async def test_health_expose_les_reglages() -> None:
    async with client(Banc()) as c:
        corps = (await c.get("/health")).json()
    assert corps["reglages"]["actuaire"]["max_tokens"] == 400
    assert corps["reglages"]["actuaire"]["version_prompt"] == corps["prompts"]["actuaire"]
    assert set(corps["reglages"]["redacteur"]) == {
        "modele", "temperature", "max_tokens", "delai_s", "version_prompt"
    }  # fmt: skip


async def test_health_reprend_les_empreintes_calculees_au_demarrage() -> None:
    banc = Banc()
    banc.deps = replace(banc.deps, versions_prompt={a: f"demarrage-{a}" for a in REGLAGES})
    async with client(banc) as c:
        corps = (await c.get("/health")).json()
    assert corps["prompts"]["actuaire"] == "demarrage-actuaire"
    assert corps["reglages"]["redacteur"]["version_prompt"] == "demarrage-redacteur"


async def test_health_503_tant_que_les_scanners_ne_sont_pas_construits() -> None:
    libere = asyncio.Event()

    @asynccontextmanager
    async def lente(_cfg: Any) -> AsyncIterator[ServiceEvaluation]:
        await libere.wait()
        yield ServiceEvaluation(Banc().deps, MemorySaver())

    app = creer_app(lente)
    app.state.config, app.state.jwks = config_cluster(), FauxJwks()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as c:
            r = await c.get("/health")
            assert r.status_code == 503
            assert r.json()["code"] == "GARDE_FOUS_EN_CHARGEMENT"
            libere.set()
            while app.state.service is None:
                await asyncio.sleep(0)
            assert (await c.get("/health")).status_code == 200


async def test_audit_agent_un_enregistrement_par_agent_sans_donnee_personnelle(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agentinsurflow_cluster.infrastructure.otel.audit import AuditOtel

    banc = Banc()
    banc.deps = Dependances(
        banc.outils, banc.redaction, banc.deps.garde, AuditOtel(), REGLAGES,
        versions_prompt={"pieces": "vp", "analyste": "va", "redacteur": "vr", "actuaire": "vc"},
    )  # fmt: skip
    monkeypatch.setattr(logging.getLogger("insurflow.audit"), "propagate", True)
    with caplog.at_level(logging.INFO, logger="insurflow.audit"):
        async with client(banc) as c:
            await c.post("/evaluations/C-1")
    registres = [r for r in caplog.records if r.name == "insurflow.audit"]
    assert [r.agent for r in registres] == [  # type: ignore[attr-defined]
        "saga", "pieces", "analyste", "redacteur", "actuaire"
    ]  # fmt: skip
    empreinte_obs = hashlib.sha256(CONTRAT["observations"].encode()).hexdigest()
    assert {r.observations_sha256 for r in registres} == {empreinte_obs}  # type: ignore[attr-defined]
    premier = registres[1]
    assert premier.getMessage() == "audit.agent"
    assert premier.numero_contrat == "C-1" and premier.mode == "llm"  # type: ignore[attr-defined]
    assert len(premier.vue_sha256) == 64 and len(premier.rapport_sha256) == 64  # type: ignore[attr-defined]
    assert premier.version_prompt == "vp" and premier.garde_fous == []  # type: ignore[attr-defined]
    # D3 : executer_agent transmet bien deps.reglages[nom] à l'audit (la Saga n'en a pas)
    assert (premier.modele, premier.max_tokens) == ("gpt-4.1-mini", 400)  # type: ignore[attr-defined]
    assert registres[0].modele is None  # type: ignore[attr-defined]
    brut = " ".join(str(vars(r)) for r in registres)
    assert "Client fidèle" not in brut and "Bearer" not in brut


async def test_openapi_documente_les_chemins_publics_de_la_gateway() -> None:
    async with client(Banc()) as c:
        chemins = (await c.get("/openapi.json")).json()["paths"]
    assert set(chemins) == {
        "/v1/souscriptions/{numero_contrat}/evaluation",
        "/v1/souscriptions/{numero_contrat}/revue",
        "/v1/souscriptions/{numero_contrat}/pause",
        "/health/cluster",
    }


def test_reglage_invalide_empeche_le_demarrage() -> None:
    """TI : une `ReglageInvalide` de la composition arrête le démarrage (pas de 503 silencieux)."""
    from fastapi.testclient import TestClient

    from agentinsurflow_cluster.domain.reglages import ReglageInvalide

    def composition(_cfg: Any) -> Any:
        raise ReglageInvalide("pieces : temperature hors [0, 1]")

    app = creer_app(composition)
    app.state.config = config_cluster()
    app.state.jwks = FauxJwks()
    with pytest.raises(ReglageInvalide), TestClient(app):
        pass


def test_composition_reelle_refuse_un_reglage_invalide_au_demarrage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TI (D2) : le vrai chemin `composition_reelle` lit `agents.toml` avant toute I/O.

    Somme des délais (4 s) > garde globale (1 s) ⇒ `ReglageInvalide`, démarrage arrêté.
    """
    from fastapi.testclient import TestClient

    from agentinsurflow_cluster.domain.reglages import ReglageInvalide

    monkeypatch.setenv("INSURFLOW_BUDGET_S", "1")
    app = creer_app()
    app.state.config = config_cluster()
    app.state.jwks = FauxJwks()
    with pytest.raises(ReglageInvalide, match="somme"), TestClient(app):
        pass
