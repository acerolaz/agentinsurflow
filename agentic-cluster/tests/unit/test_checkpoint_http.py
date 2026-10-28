"""TU — points de reprise par la gateway : faux underwriting-admin en ``httpx.MockTransport``.

Le faux met en œuvre le contrat de ``PointsDeRepriseEndpoints.cs`` (dict par clé, octets en base64,
``idx < 0`` remplacée, sinon écrite une seule fois). Aucune I/O : c'est un TU (pyramide).
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from fakes_cluster import REGLAGES, FakeAudit, FakeGarde, FakeOutils, FakeRedaction
from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.memory import MemorySaver

from agentinsurflow_cluster.application.agents import Dependances
from agentinsurflow_cluster.application.evaluation import Revue
from agentinsurflow_cluster.infrastructure.entra.config import ConfigCluster
from agentinsurflow_cluster.infrastructure.langgraph.checkpoint import checkpointer
from agentinsurflow_cluster.infrastructure.langgraph.checkpoint_http import CheckpointerHttp
from agentinsurflow_cluster.infrastructure.langgraph.graphe import ServiceEvaluation

RACINE = "/api/points-de-reprise/"


class FauxUnderwriting:
    """Dict par clé ; ``echec`` simule un 500, ``entetes`` garde les en-têtes reçus."""

    def __init__(self) -> None:
        self.points: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.ecritures: dict[tuple[str, str, str], dict[tuple[str, int], dict[str, Any]]] = {}
        self.entetes: list[httpx.Headers] = []
        self.echec = False

    def __call__(self, requete: httpx.Request) -> httpx.Response:
        self.entetes.append(requete.headers)
        if self.echec:
            return httpx.Response(500)
        chemin = requete.url.path.removeprefix(RACINE)
        q = requete.url.params
        corps = json.loads(requete.content) if requete.content else None
        if requete.method == "DELETE":
            self.points = {k: v for k, v in self.points.items() if k[0] != chemin}
            self.ecritures = {k: v for k, v in self.ecritures.items() if k[0] != chemin}
            return httpx.Response(204)
        if requete.method == "PUT" and chemin.endswith("/ecritures"):
            fil = chemin.removesuffix("/ecritures")
            tas = self.ecritures.setdefault((fil, corps["ns"], corps["checkpoint_id"]), {})
            for e in corps["ecritures"]:
                cle = (corps["task_id"], e["idx"])
                if e["idx"] >= 0 and cle in tas:
                    continue
                tas[cle] = {"task_id": corps["task_id"], "task_path": corps["task_path"], **e}
            return httpx.Response(204)
        if requete.method == "PUT":
            self.points[(chemin, corps["ns"], corps["checkpoint_id"])] = corps
            return httpx.Response(204)
        if chemin.endswith("/liste"):
            fil = chemin.removesuffix("/liste")
            ids = sorted(
                (k for k in self.points if k[0] == fil and q.get("ns") in (None, k[1])),
                key=lambda k: k[2],
                reverse=True,
            )
            if "avant" in q:
                ids = [k for k in ids if k[2] < q["avant"]]
            if "limite" in q:
                ids = ids[: int(q["limite"])]
            return httpx.Response(200, json={"points": [self._point(k) for k in ids]})
        ns = q.get("ns", "")
        if "id" in q:
            cle = (chemin, ns, q["id"])
        else:
            candidats = [k for k in self.points if k[:2] == (chemin, ns)]
            cle = max(candidats, key=lambda k: k[2]) if candidats else (chemin, ns, "")
        if cle not in self.points:
            return httpx.Response(404, json={"code": "POINT_DE_REPRISE_INTROUVABLE"})
        return httpx.Response(200, json=self._point(cle))

    def _point(self, cle: tuple[str, str, str]) -> dict[str, Any]:
        return {**self.points[cle], "ecritures": list(self.ecritures.get(cle, {}).values())}


def _saver(faux: FauxUnderwriting, jeton: str = "jeton-app") -> CheckpointerHttp:
    client = httpx.AsyncClient(transport=httpx.MockTransport(faux), base_url="http://gateway")
    return CheckpointerHttp(client, lambda: jeton)


def _cfg(fil: str = "AIF-1", ns: str = "", cid: str | None = None) -> dict[str, Any]:
    c: dict[str, Any] = {"thread_id": fil, "checkpoint_ns": ns}
    if cid:
        c["checkpoint_id"] = cid
    return {"configurable": c}


def _point(valeur: str, etape: int, parent: dict[str, Any]) -> tuple[Any, ...]:
    cp = empty_checkpoint()
    cp["channel_values"] = {"etat": {"valeur": valeur}, "n": 1}
    cp["channel_versions"] = {"etat": etape, "n": etape}
    return cp, {"source": "loop", "step": etape, "parents": {}}, {"etat": etape, "n": etape}, parent


async def _ecrire(saver: CheckpointerHttp, valeur: str, etape: int, parent: dict[str, Any]) -> Any:
    cp, meta, versions, base = _point(valeur, etape, parent)
    return await saver.aput(base, cp, meta, versions)


async def test_aput_puis_aget_tuple_rend_le_meme_point() -> None:
    saver = _saver(FauxUnderwriting())
    suivant = await _ecrire(saver, "a", 1, _cfg())
    assert suivant["configurable"]["thread_id"] == "AIF-1"
    assert suivant["configurable"]["checkpoint_id"]
    tuple_ = await saver.aget_tuple(suivant)
    assert tuple_ is not None
    assert tuple_.checkpoint["channel_values"] == {"etat": {"valeur": "a"}, "n": 1}
    assert tuple_.checkpoint["id"] == suivant["configurable"]["checkpoint_id"]
    assert tuple_.metadata["step"] == 1
    assert tuple_.parent_config is None
    assert tuple_.pending_writes == []


async def test_parent_config_rendue_pour_un_point_enfant() -> None:
    saver = _saver(FauxUnderwriting())
    premier = await _ecrire(saver, "a", 1, _cfg())
    second = await _ecrire(saver, "b", 2, premier)
    tuple_ = await saver.aget_tuple(second)
    assert tuple_ is not None
    assert tuple_.parent_config == {
        "configurable": {
            "thread_id": "AIF-1",
            "checkpoint_ns": "",
            "checkpoint_id": premier["configurable"]["checkpoint_id"],
        }
    }


async def test_aget_tuple_sans_id_rend_le_dernier() -> None:
    saver = _saver(FauxUnderwriting())
    premier = await _ecrire(saver, "a", 1, _cfg())
    second = await _ecrire(saver, "b", 2, premier)
    tuple_ = await saver.aget_tuple(_cfg())
    assert tuple_ is not None
    assert tuple_.config["configurable"]["checkpoint_id"] == second["configurable"]["checkpoint_id"]
    assert tuple_.checkpoint["channel_values"]["etat"] == {"valeur": "b"}


async def test_aget_tuple_absent_rend_none() -> None:
    saver = _saver(FauxUnderwriting())
    assert await saver.aget_tuple(_cfg("AIF-INCONNU")) is None
    assert await saver.aget_tuple(_cfg(cid="inconnu")) is None


async def test_alist_ordre_avant_limite_et_filtre_metadata() -> None:
    saver = _saver(FauxUnderwriting())
    c1 = await _ecrire(saver, "a", 1, _cfg())
    c2 = await _ecrire(saver, "b", 2, c1)
    c3 = await _ecrire(saver, "c", 3, c2)
    ids = [c["configurable"]["checkpoint_id"] for c in (c1, c2, c3)]

    tous = [t async for t in saver.alist(_cfg())]
    assert [t.config["configurable"]["checkpoint_id"] for t in tous] == ids[::-1]
    assert [t.metadata["step"] for t in tous] == [3, 2, 1]

    avant = [t async for t in saver.alist(_cfg(), before=c3)]
    assert [t.metadata["step"] for t in avant] == [2, 1]

    limite = [t async for t in saver.alist(_cfg(), limit=2)]
    assert [t.metadata["step"] for t in limite] == [3, 2]

    # le filtre porte sur les métadonnées décodées, avant la limite
    filtre = [t async for t in saver.alist(_cfg(), filter={"step": 1}, limit=1)]
    assert [t.metadata["step"] for t in filtre] == [1]
    assert [t async for t in saver.alist(_cfg(), filter={"step": 9})] == []
    assert [t async for t in saver.alist(_cfg("AIF-INCONNU"))] == []


async def test_aput_writes_puis_ecritures_en_attente_triees() -> None:
    faux = FauxUnderwriting()
    saver = _saver(faux)
    suivant = await _ecrire(saver, "a", 1, _cfg())
    await saver.aput_writes(suivant, [("canal_b", {"x": 2}), ("canal_a", 1)], "tache-2", "p")
    await saver.aput_writes(suivant, [("canal_a", "t1")], "tache-1", "p")
    # canal spécial (ERROR) : idx négatif, remplacée à la réécriture ; ordinaire : écrite une fois
    await saver.aput_writes(suivant, [("__error__", "premier")], "tache-1", "p")
    await saver.aput_writes(suivant, [("__error__", "second")], "tache-1", "p")
    await saver.aput_writes(suivant, [("canal_a", "ignoree")], "tache-1", "p")
    tuple_ = await saver.aget_tuple(suivant)
    assert tuple_ is not None
    assert tuple_.pending_writes == [
        ("tache-1", "__error__", "second"),
        ("tache-1", "canal_a", "t1"),
        ("tache-2", "canal_b", {"x": 2}),
        ("tache-2", "canal_a", 1),
    ]
    envoye = next(iter(faux.ecritures.values()))
    assert envoye[("tache-2", 1)]["canal"] == "canal_a"  # index de position
    assert envoye[("tache-1", -1)]["task_path"] == "p"


async def test_adelete_thread() -> None:
    faux = FauxUnderwriting()
    saver = _saver(faux)
    a = await _ecrire(saver, "a", 1, _cfg("AIF-1"))
    await _ecrire(saver, "b", 1, _cfg("AIF-2"))
    await saver.aput_writes(a, [("c", 1)], "t", "")
    await saver.adelete_thread("AIF-1")
    assert await saver.aget_tuple(_cfg("AIF-1")) is None
    assert await saver.aget_tuple(_cfg("AIF-2")) is not None
    assert not faux.ecritures


async def test_jeton_pose_en_bearer() -> None:
    faux = FauxUnderwriting()
    saver = _saver(faux, "abc.def")
    await _ecrire(saver, "a", 1, _cfg())
    await saver.aget_tuple(_cfg())
    assert faux.entetes and all(e["authorization"] == "Bearer abc.def" for e in faux.entetes)


@pytest.mark.parametrize("panne", ["500", "reseau", "jeton"])
async def test_erreur_remonte_sans_point_vide(panne: str) -> None:
    faux = FauxUnderwriting()
    saver = _saver(faux)
    await _ecrire(saver, "a", 1, _cfg())
    if panne == "500":
        faux.echec = True
    elif panne == "reseau":

        def coupe(_: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("injoignable")

        saver.client = httpx.AsyncClient(transport=httpx.MockTransport(coupe), base_url="http://g")
    else:

        def sans_jeton() -> str:
            raise RuntimeError("Entra indisponible")

        saver.jeton = sans_jeton
    erreur = {"500": httpx.HTTPStatusError, "reseau": httpx.ConnectError, "jeton": RuntimeError}
    with pytest.raises(erreur[panne]):
        await saver.aget_tuple(_cfg())
    with pytest.raises(erreur[panne]):
        await _ecrire(saver, "b", 2, _cfg())
    with pytest.raises(erreur[panne]):
        _ = [t async for t in saver.alist(_cfg())]


def test_les_versions_synchrones_ne_sont_pas_prises_en_charge() -> None:
    saver = _saver(FauxUnderwriting())
    with pytest.raises(NotImplementedError):
        saver.get_tuple(_cfg())
    with pytest.raises(NotImplementedError):
        saver.put(_cfg(), empty_checkpoint(), {}, {})


# --- le vrai graphe, deux « répliques » qui partagent le même faux underwriting-admin ---


def _deps() -> Dependances:
    return Dependances(
        outils=FakeOutils(),
        redaction=FakeRedaction(),
        garde=FakeGarde(),
        audit=FakeAudit(),
        reglages=REGLAGES,
        versions_prompt={"pieces": "vp", "analyste": "va", "redacteur": "vr", "actuaire": "vc"},
    )


async def test_reprise_apres_interrupt_par_http() -> None:
    faux = FauxUnderwriting()
    r1 = await ServiceEvaluation(_deps(), _saver(faux)).evaluer("C-1", "jeton", "oid-a")
    memoire = ServiceEvaluation(_deps(), MemorySaver())
    attendu = await memoire.evaluer("C-1", "jeton", "oid-a")
    assert r1.statut == attendu.statut
    assert faux.points, "des points de reprise ont été écrits par HTTP"

    # un nouveau service (redémarrage) : la revue reprend à l'étape suivante, depuis le faux seul
    revue = Revue("ACCEPTE", "VALIDEE", "Conforme au barème.")
    service2 = ServiceEvaluation(_deps(), _saver(faux))
    final = await service2.reviser("C-1", revue, "jeton", "oid-a")
    assert final.statut == "ACCEPTE"
    assert (await service2._etat("C-1")).next == ()


# --- fabrique : saver HTTP, MemorySaver ou refus au démarrage ---


def _config(**kw: Any) -> ConfigCluster:
    return ConfigCluster(_env_file=None, **kw)


_AZURE = {
    "telemetrie_audience": "api://uw",
    "azure_tenant_id": "tenant",
    "insurflow_cluster_client_id": "cluster",
    "insurflow_client_secret": "secret-de-test",
    "gateway_url": "http://gateway",
}


async def test_azure_sans_configuration_http_refuse_de_demarrer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for env in ("staging", "production"):
        monkeypatch.setenv("APP_ENV", env)
        with pytest.raises(RuntimeError, match="points de reprise"):
            async with checkpointer(_config()):
                pass
    monkeypatch.setenv("APP_ENV", "staging")  # configuration partielle : même refus
    with pytest.raises(RuntimeError):
        async with checkpointer(_config(telemetrie_audience="api://uw")):
            pass


async def test_hors_azure_sans_configuration_memory_saver(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    async with checkpointer(_config()) as saver:
        assert isinstance(saver, MemorySaver)


async def test_configuration_http_complete_donne_le_saver_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    async with checkpointer(_config(**_AZURE)) as saver:
        assert isinstance(saver, CheckpointerHttp)
        assert str(saver.client.base_url).rstrip("/") == "http://gateway"
