"""Function de calcul : adaptateur HTTP du barème et de la formule (aucune règle métier ici).

La protection est Easy Auth (niveau ANONYMOUS côté Function). Jamais de log du corps de la
requête ni de la réponse : ils contiennent les faits du dossier et les montants.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import azure.functions as func

from agentinsurflow_calcul.domain.bareme import VERSION_BAREME, evaluer
from agentinsurflow_calcul.domain.formule import VERSION_FORMULE, calculer
from agentinsurflow_calcul.domain.frequence import (
    DonneeHorsModele,
    ProfilFrequence,
    charger_modele,
    predire,
)
from agentinsurflow_calcul.domain.models import DonneeHorsBareme, FaitsPrime, FaitsRisque

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

_CHAMPS_RISQUE: dict[str, type] = {
    "suspensions": int,
    "resiliations": int,
    "crm": Decimal,
    "nb_sinistres_responsables_trois_ans": int,
    "nb_sinistres_trois_ans": int,
    "anciennete_permis_mois": int,
    "puissance_fiscale_cv": int,
}
_CHAMPS_PRIME: dict[str, type] = {
    "formule": str,
    "anciennete_permis_mois": int,
    "departement": str,
    "puissance_fiscale_cv": int,
    "type_usage": str,
    "crm": Decimal,
}
_CHAMPS_FREQUENCE: dict[str, type] = {
    "crm": Decimal,
    "puissance_fiscale_cv": int,
    "departement": str,
}
_DECIMAL_STRICT = re.compile(r"[0-9]+(\.[0-9]+)?")  # ni exposant, espace, signe, NaN


class _RequeteInvalide(Exception):
    """Corps non conforme au contrat (400) ; ne porte jamais de valeur du dossier."""


def _json(statut: int, corps: dict[str, Any]) -> func.HttpResponse:
    return func.HttpResponse(json.dumps(corps), status_code=statut, mimetype="application/json")


def _valeur(type_attendu: type, valeur: object) -> object:
    if valeur is None:
        return None
    if type_attendu is int and isinstance(valeur, int) and not isinstance(valeur, bool):
        return valeur
    if type_attendu is str and isinstance(valeur, str):
        return valeur
    if type_attendu is Decimal and isinstance(valeur, str) and _DECIMAL_STRICT.fullmatch(valeur):
        return Decimal(valeur)
    raise _RequeteInvalide


def _faits(req: func.HttpRequest, champs: dict[str, type]) -> dict[str, object]:
    """Corps JSON strict : un objet avec exactement ``champs``, du bon type ou ``null``."""
    try:
        corps = json.loads(req.get_body())
    except ValueError:  # JSON invalide ou corps non UTF-8
        raise _RequeteInvalide from None
    if not isinstance(corps, dict) or set(corps) != set(champs):
        raise _RequeteInvalide
    return {nom: _valeur(type_attendu, corps[nom]) for nom, type_attendu in champs.items()}


def _executer(
    req: func.HttpRequest,
    champs: dict[str, type],
    traiter: Callable[[dict[str, object]], dict[str, Any]],
) -> func.HttpResponse:
    """400 corps non conforme, 422 donnée hors barème ou hors modèle, sinon 200."""
    try:
        return _json(200, traiter(_faits(req, champs)))
    except _RequeteInvalide:
        return _json(400, {"code": "REQUETE_INVALIDE"})
    except DonneeHorsBareme as e:
        return _json(422, {"code": "DONNEE_HORS_BAREME", "champ": e.champ})
    except DonneeHorsModele as e:
        return _json(422, {"code": "DONNEE_HORS_MODELE", "champ": e.champ})


def _risque(faits: dict[str, object]) -> dict[str, Any]:
    resultat = evaluer(FaitsRisque(**faits))  # type: ignore[arg-type]
    return {
        "version_bareme": resultat.version_bareme,
        "classe": resultat.classe,
        "decision": resultat.decision,
        "score": resultat.score,
        "regles": [{"regle_id": r.regle_id, "motif": r.motif} for r in resultat.regles],
    }


def _prime(faits: dict[str, object]) -> dict[str, Any]:
    resultat = calculer(FaitsPrime(**faits))  # type: ignore[arg-type]
    return {
        "version_formule": resultat.version_formule,
        "prime_ht": str(resultat.prime_ht),
        "montant_taxes": str(resultat.montant_taxes),
        "prime_ttc_annuelle": str(resultat.prime_ttc_annuelle),
        "prime_mensuelle": str(resultat.prime_mensuelle),
        "coefficients": {k: str(v) for k, v in resultat.coefficients.items()},
    }


def _frequence(faits: dict[str, object]) -> dict[str, Any]:
    p = predire(charger_modele(), ProfilFrequence(**faits))  # type: ignore[arg-type]
    # version et fréquence seulement : jamais de donnée du profil
    logging.info("glm.frequence version=%s frequence=%.4f", p.version_modele, p.frequence_annuelle)
    return {
        "version_modele": p.version_modele,
        "frequence_annuelle": p.frequence_annuelle,
        "variables": ["BonusMalus", "VehPower", "Region"],
    }


@app.function_name(name="evaluer")
@app.route(route="evaluer", methods=["POST"])
def evaluer_route(req: func.HttpRequest) -> func.HttpResponse:
    return _executer(req, _CHAMPS_RISQUE, _risque)


@app.function_name(name="calculer")
@app.route(route="calculer", methods=["POST"])
def calculer_route(req: func.HttpRequest) -> func.HttpResponse:
    return _executer(req, _CHAMPS_PRIME, _prime)


@app.function_name(name="frequence")
@app.route(route="frequence", methods=["POST"])
def frequence_route(req: func.HttpRequest) -> func.HttpResponse:
    """Comparaison seulement : la fréquence n'entre ni dans la décision ni dans la prime."""
    return _executer(req, _CHAMPS_FREQUENCE, _frequence)


@app.function_name(name="sante")
@app.route(route="sante", methods=["GET"])
def sante_route(req: func.HttpRequest) -> func.HttpResponse:
    return _json(
        200,
        {
            "version": os.environ.get("APP_VERSION", "dev"),
            "bareme": VERSION_BAREME,
            "formule": VERSION_FORMULE,
            "modele_frequence": charger_modele()["version"],
        },
    )
