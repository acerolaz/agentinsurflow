"""Unitaires — client PISTE / Légifrance (HTTP simulé en mémoire, pauses remplacées) et envoi
des lots à l'API (sans réseau, sans fichier).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from opentelemetry.sdk.trace import TracerProvider

from agentinsurflow_rag.cli.ingest import ErreurEnvoi, cumuler, envoyer
from agentinsurflow_rag.infrastructure.legifrance.client import (
    ConfigLegifrance,
    ErreurPiste,
    appeler,
    dans_le_perimetre,
    extraire,
    jeton_piste,
    vers_article_entrant,
)

CFG = ConfigLegifrance(
    _env_file=None,  # type: ignore[call-arg]
    legifrance_client_id="id",
    legifrance_client_secret="secret",
)

ARTICLE_LF = {
    "id": "LEGIARTI000041000001",
    "cid": "LEGIARTI000006800836",
    "num": "L211-1",
    "etat": "VIGUEUR",
    "dateDebut": 1041379200000,  # 2003-01-01 en millisecondes
    "texteHtml": "<p>Toute personne physique ou morale…</p>",
}


def _client(repondre: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(repondre))


# ---------------------------------------------------------------- PISTE


def test_jeton_piste_client_credentials() -> None:
    recu: list[httpx.Request] = []

    def repondre(requete: httpx.Request) -> httpx.Response:
        recu.append(requete)
        return httpx.Response(200, json={"access_token": "jeton-piste"})

    assert jeton_piste(_client(repondre), CFG) == "jeton-piste"
    corps = dict(x.split("=") for x in recu[0].content.decode().split("&"))
    assert corps["grant_type"] == "client_credentials" and corps["client_id"] == "id"


def test_401_piste_message_clair() -> None:
    with pytest.raises(ErreurPiste, match="identifiants PISTE invalides"):
        jeton_piste(_client(lambda r: httpx.Response(401)), CFG)


def test_429_puis_succes_trois_tentatives() -> None:
    reponses = iter([httpx.Response(429), httpx.Response(503), httpx.Response(200, json={"ok": 1})])
    pauses: list[float] = []
    resultat = appeler(
        _client(lambda r: next(reponses)), "/consult/x", {}, "j", pause=pauses.append, cfg=CFG
    )
    assert resultat == {"ok": 1} and pauses == [1, 2]


def test_echec_apres_trois_nouvelles_tentatives() -> None:
    pauses: list[float] = []
    with pytest.raises(ErreurPiste):
        appeler(
            _client(lambda r: httpx.Response(500)),
            "/consult/x",
            {},
            "j",
            pause=pauses.append,
            cfg=CFG,
        )
    assert pauses == [1, 2, 4]


def test_401_sur_l_api_message_clair() -> None:
    with pytest.raises(ErreurPiste, match="identifiants PISTE invalides"):
        appeler(_client(lambda r: httpx.Response(401)), "/consult/x", {}, "j", pause=print, cfg=CFG)


@pytest.mark.parametrize(
    ("numero", "garde"),
    [
        ("L211-1", True),
        ("L. 211-1", True),
        ("A121-1", True),
        ("R211-45", True),
        ("A211-1-2", True),
        ("L121-12", True),
        ("L112-1", False),
        ("A121-10", False),
        ("R121-1", False),
    ],
)
def test_perimetre(numero: str, garde: bool) -> None:
    assert dans_le_perimetre(numero) is garde


def test_extraire_ne_garde_que_le_perimetre() -> None:
    plan = {
        "sections": [
            {
                "articles": [
                    {"id": "A1", "num": "L211-1"},
                    {"id": "A2", "num": "L112-1"},
                ],
                "sections": [
                    {"articles": [{"id": "A3", "num": "A121-1"}, {"id": "A4", "num": "A121-10"}]}
                ],
            }
        ]
    }
    demandes: list[str] = []

    def repondre(requete: httpx.Request) -> httpx.Response:
        if requete.url.path.endswith("/consult/code/tableMatieres"):
            return httpx.Response(200, json=plan)
        identifiant = json.loads(requete.content)["id"]
        demandes.append(identifiant)
        return httpx.Response(200, json={"article": ARTICLE_LF | {"id": identifiant}})

    articles = extraire(_client(repondre), CFG, "j", "2026-10-19", pause=print)
    assert demandes == ["A1", "A3"]
    assert [a["version"] for a in articles] == ["A1", "A3"]


def test_vers_article_entrant() -> None:
    assert vers_article_entrant(ARTICLE_LF) == {
        "doc_id": "LEGIARTI000006800836",
        "version": "LEGIARTI000041000001",
        "article": "L211-1",
        "date_debut": "2003-01-01",
        "etat": "VIGUEUR",
        "texte_html": "<p>Toute personne physique ou morale…</p>",
        "url_source": "https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000041000001",
    }


def test_vers_article_entrant_champs_absents_restent_absents() -> None:
    # le serveur rejette l'article partiel avec sa raison (spec §3.2 ⑤), la CLI ne devine rien
    entrant = vers_article_entrant({"id": "X"})
    assert (
        entrant["doc_id"] is None
        and entrant["texte_html"] is None
        and entrant["date_debut"] is None
    )


# ---------------------------------------------------------------- envoi par lots


def _articles(n: int) -> list[dict[str, Any]]:
    return [{"doc_id": f"D{i}"} for i in range(n)]


def _api(recu: list[httpx.Request], statut: int = 201) -> httpx.Client:
    def repondre(requete: httpx.Request) -> httpx.Response:
        recu.append(requete)
        lot = json.loads(requete.content)["articles"]
        return httpx.Response(
            statut,
            json={"id": len(recu), "lus": len(lot), "inseres": len(lot), "inchanges": 0,
                  "nouvelles_versions": 0, "rejets": [], "quasi_doublons": [], "duree_s": 0.1},
        )  # fmt: skip

    return _client(repondre)


def test_envoi_par_lots_de_50() -> None:
    recu: list[httpx.Request] = []
    tracer = TracerProvider().get_tracer("test")
    rapport = envoyer(_api(recu), "http://gw", "jeton", _articles(120), "f" * 64, tracer)
    assert [len(json.loads(r.content)["articles"]) for r in recu] == [50, 50, 20]
    assert recu[0].url.path == "/api/ingestions"
    assert recu[0].headers["authorization"] == "Bearer jeton"
    assert (rapport["lus"], rapport["inseres"], rapport["ingestions"]) == (120, 120, [1, 2, 3])


def test_traceparent_injecte_dans_chaque_lot_meme_trace() -> None:
    recu: list[httpx.Request] = []
    tracer = TracerProvider().get_tracer("test")
    with tracer.start_as_current_span("ingest.run"):
        envoyer(_api(recu), "http://gw", "jeton", _articles(60), "f" * 64, tracer)
    traces = {r.headers["traceparent"].split("-")[1] for r in recu}
    assert len(recu) == 2 and len(traces) == 1


def test_lot_refuse_erreur_envoi() -> None:
    with pytest.raises(ErreurEnvoi, match="403"):
        envoyer(
            _api([], statut=403),
            "http://gw",
            "j",
            _articles(1),
            "f" * 64,
            TracerProvider().get_tracer("t"),
        )


def test_cumuler_les_rapports() -> None:
    total = cumuler(
        [
            {"id": 1, "lus": 2, "inseres": 1, "inchanges": 1, "nouvelles_versions": 0,
             "rejets": [{"doc_id": "X", "raison": "vide"}], "quasi_doublons": [], "duree_s": 0.5},
            {"id": 2, "lus": 1, "inseres": 0, "inchanges": 0, "nouvelles_versions": 1,
             "rejets": [], "quasi_doublons": [{"doc_id": "A", "proche_de": "B", "score": 0.97}],
             "duree_s": 0.25},
        ]
    )  # fmt: skip
    assert total == {
        "ingestions": [1, 2],
        "lus": 3,
        "inseres": 1,
        "inchanges": 1,
        "nouvelles_versions": 1,
        "rejets": [{"doc_id": "X", "raison": "vide"}],
        "quasi_doublons": [{"doc_id": "A", "proche_de": "B", "score": 0.97}],
        "duree_s": 0.75,
    }
