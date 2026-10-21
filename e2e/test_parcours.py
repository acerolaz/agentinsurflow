"""Parcours bout en bout, chaque appel passant par la gateway (``E2E_URL``)."""

from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path

import httpx
import pytest

RACINE = Path(__file__).resolve().parent.parent
QUESTION_COUVERTE = "Que prévoit l'article L. 211-1 du Code des assurances ?"
QUESTION_HORS_CORPUS = "Quelle est la recette de la blanquette de veau ?"
CONTRAT_AUTRE = "AIF-2026-000004"  # seed : gestionnaire B (A possède 000001 à 000003)
CONTRAT_INCONNU = "AIF-9999-9999"
SERVICES_ATTENDUS = ("gateway", "rag", "underwriting")


def bearer(jeton: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {jeton}"}


CODES_ATTENDUS = {"EMBEDDINGS_INDISPONIBLES", "DOSSIERS_INDISPONIBLES"}


def _manque_si_indisponible(r: httpx.Response, manque) -> None:
    """Seul un 503 au code attendu est un manque d'environnement ; tout autre 503 est un échec."""
    if r.status_code != 503:
        return
    try:
        code = r.json().get("code")
    except ValueError:
        code = None
    if code in CODES_ATTENDUS:
        manque(f"{code} (HTTP 503)")
    pytest.fail(f"503 inattendu : {r.text[:300]}")


def _poser(client, manque, jeton: str, corps: dict) -> httpx.Response:
    r = client.post("/api/reponses", json=corps, headers=bearer(jeton))
    _manque_si_indisponible(r, manque)
    return r


def test_seule_la_gateway_est_exposee(url, local, client):
    if local:
        pytest.skip("staging seulement : le compose publie rag et underwriting-admin pour le debug")
    assert client.get("/health").status_code == 200
    hote = httpx.URL(url).host
    for port in (8001, 8002):
        with pytest.raises(httpx.TransportError):
            httpx.get(f"http://{hote}:{port}/health", timeout=5)


def test_ingestion_rejouee_zero_insere(url, jeton_ingestion, manque):
    instantane = max((RACINE / "data/raw").glob("*.json"), default=None)
    if instantane is None:
        manque("aucun instantané dans data/raw/ à rejouer")
    env = {**os.environ, "INGESTION_JETON": jeton_ingestion}
    cmd = ["make", "ingest", f"URL={url}", f"INSTANTANE={instantane.relative_to(RACINE)}"]
    sorties = [
        subprocess.run(cmd, cwd=RACINE, env=env, capture_output=True, text=True, timeout=600)
        for _ in range(2)
    ]
    for s in sorties:
        if "EMBEDDINGS_INDISPONIBLES" in s.stdout + s.stderr:
            manque("EMBEDDINGS_INDISPONIBLES (HTTP 503)")
        assert s.returncode == 0, s.stderr[-500:]
    assert re.search(r"✔ 0 insérés", sorties[1].stdout), sorties[1].stdout[-500:]


def test_question_couverte_citee_et_tracable(
    client, manque, jeton_gestionnaire, jeton_gestionnaire_underwriting
):
    r = _poser(client, manque, jeton_gestionnaire, {"texte": QUESTION_COUVERTE})
    assert r.status_code == 200, r.text
    corps = r.json()
    assert corps["statut"] == "OK" and corps["citations"]
    assert corps["trace_id"]

    # les spans sont exportés par lots : on attend leur arrivée dans la table span
    services: set[str] = set()
    for _ in range(20):
        t = client.get(
            f"/api/traces/{corps['trace_id']}", headers=bearer(jeton_gestionnaire_underwriting)
        )
        if t.status_code == 200:
            services = {s["service_name"].lower() for s in t.json()}
            if all(any(a in nom for nom in services) for a in SERVICES_ATTENDUS):
                break
        time.sleep(1)
    for attendu in SERVICES_ATTENDUS:
        assert any(attendu in nom for nom in services), f"aucun span {attendu} : {services}"


def test_question_hors_corpus_refusee(client, manque, jeton_gestionnaire):
    r = _poser(client, manque, jeton_gestionnaire, {"texte": QUESTION_HORS_CORPUS})
    assert r.status_code == 200, r.text
    corps = r.json()
    assert corps["statut"] == "NOT_FOUND_IN_CORPUS"
    assert corps["citations"] == []
    assert corps["texte"].startswith("Je ne trouve pas la réponse dans le corpus")


def test_contrat_d_un_autre_gestionnaire_404(
    client, contrat_propre, jeton_gestionnaire_underwriting
):
    # via /api/contrats : un contrat d'un autre gestionnaire est indiscernable d'un contrat inconnu
    h = bearer(jeton_gestionnaire_underwriting)
    autre = client.get(f"/api/contrats/{CONTRAT_AUTRE}", headers=h)
    inconnu = client.get(f"/api/contrats/{CONTRAT_INCONNU}", headers=h)
    assert autre.status_code == inconnu.status_code == 404
    assert autre.json() == inconnu.json()
    assert autre.json()["code"] == "CONTRAT_INTROUVABLE"

    # témoin positif : le gestionnaire connecté voit son propre contrat, et seulement le sien
    # ponytail: sans E2E_CONTRAT_PROPRE (local seulement), ce témoin est omis
    if contrat_propre:
        assert client.get(f"/api/contrats/{contrat_propre}", headers=h).status_code == 200
        liste = client.get("/api/contrats?limit=100", headers=h)
        assert liste.status_code == 200
        numeros = {c["numero_contrat"] for c in liste.json()}
        assert contrat_propre in numeros and CONTRAT_AUTRE not in numeros


def test_contrat_d_un_autre_gestionnaire_404_via_reponses(client, manque, jeton_gestionnaire):
    """Chemin OBO : même refus, rien du dossier n'est révélé."""
    r = _poser(
        client,
        manque,
        jeton_gestionnaire,
        {"texte": QUESTION_COUVERTE, "numero_contrat": CONTRAT_AUTRE},
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "CONTRAT_INTROUVABLE"


def test_v1_traces_sans_jeton_refuse_depuis_l_exterieur(client):
    r = client.post("/v1/traces", content=b"", headers={"Content-Type": "application/x-protobuf"})
    assert r.status_code in (401, 403)


def test_ip_client_reelle_dans_les_spans(
    local, client, manque, jeton_gestionnaire, jeton_gestionnaire_underwriting
):
    """S3-26 : le span de la gateway porte l'IP publique du poste de test, pas celle de l'envoy."""
    if local:
        pytest.skip("staging seulement : en local il n'y a pas d'envoy ni d'IP publique")
    ip = httpx.get("https://api.ipify.org", timeout=10).text.strip()
    r = _poser(client, manque, jeton_gestionnaire, {"texte": QUESTION_COUVERTE})
    assert r.status_code == 200, r.text
    spans: list[dict] = []
    for _ in range(20):
        t = client.get(
            f"/api/traces/{r.json()['trace_id']}", headers=bearer(jeton_gestionnaire_underwriting)
        )
        spans = t.json() if t.status_code == 200 else []
        if any("gateway" in s["service_name"].lower() for s in spans):
            break
        time.sleep(1)
    adresses = {
        s["attributes"].get("client.address")
        for s in spans
        if "gateway" in s["service_name"].lower()
    }
    assert ip in adresses, f"client.address = {adresses}, attendu {ip}"
