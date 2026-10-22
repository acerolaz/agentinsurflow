"""Function de calcul : adaptateur HTTP du barème et de la formule (aucune règle métier ici).

La protection est Easy Auth (niveau ANONYMOUS côté Function). Jamais de log du corps de la
requête ni de la réponse : ils contiennent les faits du dossier et les montants.
"""

from __future__ import annotations

import json
import os
from decimal import Decimal, InvalidOperation
from typing import Any

import azure.functions as func

from agentinsurflow_calcul.domain.bareme import VERSION_BAREME, evaluer
from agentinsurflow_calcul.domain.formule import VERSION_FORMULE, calculer
from agentinsurflow_calcul.domain.models import DonneeHorsBareme, FaitsPrime, FaitsRisque

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

_ENTIER, _CHAINE, _DECIMAL = "entier", "chaine", "decimal"
_CHAMPS_RISQUE = {
    "suspensions": _ENTIER,
    "resiliations": _ENTIER,
    "crm": _DECIMAL,
    "nb_sinistres_responsables_trois_ans": _ENTIER,
    "nb_sinistres_trois_ans": _ENTIER,
    "anciennete_permis_mois": _ENTIER,
    "puissance_fiscale_cv": _ENTIER,
}
_CHAMPS_PRIME = {
    "formule": _CHAINE,
    "anciennete_permis_mois": _ENTIER,
    "departement": _CHAINE,
    "puissance_fiscale_cv": _ENTIER,
    "type_usage": _CHAINE,
    "crm": _DECIMAL,
}


class _RequeteInvalide(Exception):
    """Corps non conforme au contrat (400) ; ne porte jamais de valeur du dossier."""


def _json(statut: int, corps: dict[str, Any]) -> func.HttpResponse:
    return func.HttpResponse(json.dumps(corps), status_code=statut, mimetype="application/json")


def _valeur(type_attendu: str, valeur: object) -> object:
    if valeur is None:
        return None
    if type_attendu == _ENTIER and isinstance(valeur, int) and not isinstance(valeur, bool):
        return valeur
    if type_attendu == _CHAINE and isinstance(valeur, str):
        return valeur
    if type_attendu == _DECIMAL and isinstance(valeur, str):
        try:
            decimal = Decimal(valeur)
        except InvalidOperation:
            raise _RequeteInvalide from None
        if decimal.is_finite():
            return decimal
    raise _RequeteInvalide


def _faits(req: func.HttpRequest, champs: dict[str, str]) -> dict[str, object]:
    """Corps JSON strict : un objet avec exactement ``champs``, du bon type ou ``null``."""
    try:
        corps = json.loads(req.get_body())
    except ValueError:  # JSON invalide ou corps non UTF-8
        raise _RequeteInvalide from None
    if not isinstance(corps, dict) or set(corps) != set(champs):
        raise _RequeteInvalide
    return {nom: _valeur(type_attendu, corps[nom]) for nom, type_attendu in champs.items()}


@app.function_name(name="evaluer")
@app.route(route="evaluer", methods=["POST"])
def evaluer_route(req: func.HttpRequest) -> func.HttpResponse:
    try:
        resultat = evaluer(FaitsRisque(**_faits(req, _CHAMPS_RISQUE)))  # type: ignore[arg-type]
    except _RequeteInvalide:
        return _json(400, {"code": "REQUETE_INVALIDE"})
    except DonneeHorsBareme as e:
        return _json(422, {"code": "DONNEE_HORS_BAREME", "champ": e.champ})
    return _json(
        200,
        {
            "version_bareme": resultat.version_bareme,
            "classe": resultat.classe,
            "decision": resultat.decision,
            "score": resultat.score,
            "regles": [{"regle_id": r.regle_id, "motif": r.motif} for r in resultat.regles],
        },
    )


@app.function_name(name="calculer")
@app.route(route="calculer", methods=["POST"])
def calculer_route(req: func.HttpRequest) -> func.HttpResponse:
    try:
        resultat = calculer(FaitsPrime(**_faits(req, _CHAMPS_PRIME)))  # type: ignore[arg-type]
    except _RequeteInvalide:
        return _json(400, {"code": "REQUETE_INVALIDE"})
    except DonneeHorsBareme as e:
        return _json(422, {"code": "DONNEE_HORS_BAREME", "champ": e.champ})
    return _json(
        200,
        {
            "version_formule": resultat.version_formule,
            "prime_ht": str(resultat.prime_ht),
            "montant_taxes": str(resultat.montant_taxes),
            "prime_ttc_annuelle": str(resultat.prime_ttc_annuelle),
            "prime_mensuelle": str(resultat.prime_mensuelle),
            "coefficients": {k: str(v) for k, v in resultat.coefficients.items()},
        },
    )


@app.function_name(name="sante")
@app.route(route="sante", methods=["GET"])
def sante_route(req: func.HttpRequest) -> func.HttpResponse:
    return _json(
        200,
        {
            "version": os.environ.get("APP_VERSION", "dev"),
            "bareme": VERSION_BAREME,
            "formule": VERSION_FORMULE,
        },
    )
