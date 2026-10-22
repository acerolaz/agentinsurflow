"""Routes HTTP de la Function : contrat JSON, validation stricte, 400 / 422."""

from __future__ import annotations

import json

import azure.functions as func
import pytest
from function_app import app

FAITS_RISQUE = {
    "suspensions": 0,
    "resiliations": 0,
    "crm": "0.90",
    "nb_sinistres_responsables_trois_ans": 0,
    "nb_sinistres_trois_ans": 0,
    "anciennete_permis_mois": 91,
    "puissance_fiscale_cv": 5,
}
FAITS_PRIME = {
    "formule": "tous_risques",
    "anciennete_permis_mois": 91,
    "departement": "75",
    "puissance_fiscale_cv": 5,
    "type_usage": "prive",
    "crm": "0.90",
}


# get_functions() n'est pas rappelable (azure-functions 1.25 : noms « en double » au 2e appel)
FONCTIONS = {f.get_function_name(): f for f in app.get_functions()}


def appeler(
    nom: str, corps: object = None, methode: str = "POST", brut: bytes | None = None
) -> func.HttpResponse:
    fn = FONCTIONS[nom]
    body = brut if brut is not None else (b"" if corps is None else json.dumps(corps).encode())
    return fn.get_user_function()(func.HttpRequest(methode, f"/api/{nom}", body=body))


def _sans(faits: dict, cle: str) -> dict:
    return {k: v for k, v in faits.items() if k != cle}


def test_evaluer_seed_1():
    r = appeler("evaluer", FAITS_RISQUE)
    assert r.status_code == 200
    assert json.loads(r.get_body()) == {
        "version_bareme": "bareme-2026.10-v1",
        "classe": "acceptable",
        "decision": "ACCEPTE",
        "score": 0.0,
        "regles": [],
    }


def test_evaluer_regle_declenchee():
    r = appeler("evaluer", {**FAITS_RISQUE, "suspensions": 1})
    corps = json.loads(r.get_body())
    assert corps["decision"] == "REFUSE"
    assert [x["regle_id"] for x in corps["regles"]] == ["R01_SUSPENSION"]
    assert set(corps["regles"][0]) == {"regle_id", "motif"}


def test_calculer_seed_1():
    r = appeler("calculer", FAITS_PRIME)
    corps = json.loads(r.get_body())
    assert r.status_code == 200
    assert set(corps) == {
        "version_formule",
        "prime_ht",
        "montant_taxes",
        "prime_ttc_annuelle",
        "prime_mensuelle",
        "coefficients",
    }
    assert corps["prime_ttc_annuelle"] == "819.73"
    assert corps["coefficients"]["taux_taxe"] == "0.18"


@pytest.mark.parametrize(
    ("nom", "faits", "champ"),
    [
        ("evaluer", {**FAITS_RISQUE, "crm": None}, "crm"),
        ("calculer", {**FAITS_PRIME, "crm": None}, "crm"),
        ("calculer", {**FAITS_PRIME, "type_usage": "PROMENADE"}, "type_usage"),
    ],
)
def test_donnee_hors_bareme_422(nom, faits, champ):
    r = appeler(nom, faits)
    assert r.status_code == 422
    assert json.loads(r.get_body()) == {"code": "DONNEE_HORS_BAREME", "champ": champ}


@pytest.mark.parametrize(
    ("nom", "kwargs"),
    [
        ("evaluer", {"brut": b"{"}),
        ("evaluer", {"corps": []}),
        ("evaluer", {"corps": _sans(FAITS_RISQUE, "suspensions")}),
        ("evaluer", {"corps": {**FAITS_RISQUE, "inconnu": 1}}),
        ("evaluer", {"corps": {**FAITS_RISQUE, "suspensions": True}}),
        ("evaluer", {"corps": {**FAITS_RISQUE, "suspensions": "1"}}),
        ("evaluer", {"corps": {**FAITS_RISQUE, "crm": 0.9}}),
        ("evaluer", {"corps": {**FAITS_RISQUE, "crm": "abc"}}),
        ("calculer", {"brut": b""}),
        ("calculer", {"corps": _sans(FAITS_PRIME, "departement")}),
        ("calculer", {"corps": {**FAITS_PRIME, "inconnu": 1}}),
        ("calculer", {"corps": {**FAITS_PRIME, "departement": 75}}),
        ("calculer", {"corps": {**FAITS_PRIME, "puissance_fiscale_cv": True}}),
        ("calculer", {"corps": {**FAITS_PRIME, "crm": 0.9}}),
    ],
)
def test_requete_invalide_400(nom, kwargs):
    r = appeler(nom, **kwargs)
    assert r.status_code == 400
    assert json.loads(r.get_body()) == {"code": "REQUETE_INVALIDE"}


def test_sante(monkeypatch):
    monkeypatch.delenv("APP_VERSION", raising=False)
    r = appeler("sante", methode="GET")
    assert r.status_code == 200
    assert json.loads(r.get_body()) == {
        "version": "dev",
        "bareme": "bareme-2026.10-v1",
        "formule": "formule-2026.10-v1",
    }


def test_sante_version_depuis_l_environnement(monkeypatch):
    monkeypatch.setenv("APP_VERSION", "abc123")
    assert json.loads(appeler("sante", methode="GET").get_body())["version"] == "abc123"
