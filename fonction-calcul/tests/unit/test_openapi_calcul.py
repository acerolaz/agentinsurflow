"""Non-dérive du document OpenAPI de la Function (C9) : code ⇔ document, vu depuis la gateway.

Les routes sont lues dans le source (``ast``) : ``app.get_functions()`` ne se rappelle pas.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import function_app
import pytest
from jsonschema import Draft202012Validator, ValidationError

RACINE = Path(__file__).resolve().parents[3]
SOURCE = Path(function_app.__file__).read_text(encoding="utf-8")
DOCUMENT = json.loads((RACINE / "docs/openapi/fonction-calcul.json").read_text(encoding="utf-8"))
ROUTES_GATEWAY = json.loads(
    (RACINE / "gateway/src/AgentInsurFlow.Gateway.Api/appsettings.Routes.json").read_text(
        encoding="utf-8"
    )
)["ReverseProxy"]["Routes"]

EXEMPLES = {  # corps acceptés par la Function (tests de test_routes_calcul.py)
    "FaitsRisque": {
        "suspensions": 0,
        "resiliations": 0,
        "crm": "0.90",
        "nb_sinistres_responsables_trois_ans": 0,
        "nb_sinistres_trois_ans": 0,
        "anciennete_permis_mois": 91,
        "puissance_fiscale_cv": 5,
    },
    "ProfilFrequence": {"crm": "0.90", "puissance_fiscale_cv": 5, "departement": None},
}


def _routes_du_code() -> dict[str, tuple[str, str | None]]:
    """route → (méthode, nom du dictionnaire de champs passé à ``_executer``)."""
    routes = {}
    for f in ast.parse(SOURCE).body:
        if not isinstance(f, ast.FunctionDef):
            continue
        for d in f.decorator_list:
            if isinstance(d, ast.Call) and getattr(d.func, "attr", None) == "route":
                kw = {k.arg: ast.literal_eval(k.value) for k in d.keywords}
                appels = [
                    n
                    for n in ast.walk(f)
                    if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "_executer"
                ]
                champs = appels[0].args[1].id if appels else None  # type: ignore[attr-defined]
                (methode,) = kw["methods"]
                routes[kw["route"]] = (methode, champs)
    return routes


def _chemin_public(route: str) -> str:
    """Chemin vu depuis la gateway : inverse ``PathPattern``/``PathSet`` du cluster ``calcul``."""
    calcul = [r for r in ROUTES_GATEWAY.values() if r["ClusterId"] == "calcul"]
    for r in calcul:  # PathSet exact d'abord : il l'emporte sur le motif générique
        if any(t.get("PathSet") == f"/api/{route}" for t in r["Transforms"]):
            return str(r["Match"]["Path"])
    for r in calcul:
        if any(t.get("PathPattern") == "/api/{**reste}" for t in r["Transforms"]):
            return str(r["Match"]["Path"]).replace("{**reste}", route)
    raise AssertionError(f"route {route} absente de la gateway")


def _operations() -> dict[tuple[str, str], dict]:
    return {
        (m.upper(), chemin): op
        for chemin, ops in DOCUMENT["paths"].items()
        for m, op in ops.items()
    }


def _schema(ref: str) -> dict:
    return DOCUMENT["components"]["schemas"][ref.rsplit("/", 1)[1]]


def test_chaque_route_du_code_est_documentee_et_inversement() -> None:
    code = {(m, _chemin_public(r)) for r, (m, _) in _routes_du_code().items()}

    assert code == set(_operations())


@pytest.mark.parametrize("route", [r for r, (_, c) in _routes_du_code().items() if c])
def test_corps_documente_egal_aux_champs_de_executer(route: str) -> None:
    methode, champs = _routes_du_code()[route]
    op = _operations()[(methode, _chemin_public(route))]
    schema = _schema(op["requestBody"]["content"]["application/json"]["schema"]["$ref"])

    attendus = set(getattr(function_app, champs))  # type: ignore[arg-type]
    assert set(schema["required"]) == attendus
    assert set(schema["properties"]) == attendus
    assert schema["additionalProperties"] is False


def test_codes_d_erreur_du_code_tous_documentes() -> None:
    codes = set(re.findall(r'"code": "([A-Z_]+)"', SOURCE))
    erreur = DOCUMENT["components"]["schemas"]["ErreurCalcul"]
    documentes = set(erreur["properties"]["code"]["enum"])

    assert codes == documentes == {"REQUETE_INVALIDE", "DONNEE_HORS_BAREME", "DONNEE_HORS_MODELE"}
    for (methode, _), op in _operations().items():
        if methode == "POST":
            assert {"200", "400", "401", "403", "422", "429"} <= set(op["responses"])


def test_sante_anonyme_sans_503() -> None:
    op = _operations()[("GET", _chemin_public("sante"))]

    assert op["security"] == []
    assert set(op["responses"]) == {"200"}  # aucun 503 dans sante_route


@pytest.mark.parametrize("nom", sorted(EXEMPLES))
def test_un_corps_accepte_par_la_function_valide_le_schema(nom: str) -> None:
    schema = {**_schema(f"#/{nom}"), "components": DOCUMENT["components"]}  # $ref résolus

    Draft202012Validator(schema).validate(EXEMPLES[nom])
    with pytest.raises(ValidationError, match="Additional properties"):
        Draft202012Validator(schema).validate({**EXEMPLES[nom], "intrus": 1})
