"""TU — ``tools/az_reessayer.py`` : erreurs passagères d'Azure rejouées, les autres non (#135)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from tools.az_reessayer import TENTATIVES, executer

WORKFLOW = Path(__file__).parents[2] / ".github/workflows/deploy.yml"
UPDATE = ["az", "containerapp", "update", "-n", "app", "-g", "rg", "--yaml"]


class Azure:
    """Rend les réponses prévues dans l'ordre et note les commandes reçues."""

    def __init__(self, *reponses: tuple[int, str]) -> None:
        self.reponses = list(reponses)
        self.commandes: list[list[str]] = []

    def __call__(self, commande: list[str]) -> CompletedProcess[str]:
        self.commandes.append(commande)
        code, sortie = self.reponses.pop(0)
        return CompletedProcess(commande, code, sortie if code == 0 else "", sortie if code else "")


def lancer(azure: Azure, commande: list[str]) -> tuple[int, list[float]]:
    pauses: list[float] = []
    return executer(commande, azure, pauses.append), pauses


def test_succes_du_premier_coup_sans_pause() -> None:
    azure = Azure((0, "ok"))
    assert lancer(azure, ["az", "x"]) == (0, [])


@pytest.mark.parametrize(
    "erreur",
    [
        "HTTPError: Service Unavailable",
        "(TooManyRequests) Too many requests",
        "Operation returned an invalid status 'Bad Gateway' code 502",
        "HTTP 429",
    ],
)
def test_erreur_passagere_rejouee_puis_succes(erreur: str) -> None:
    azure = Azure((1, erreur), (0, "ok"))
    code, pauses = lancer(azure, ["az", "x"])
    assert code == 0 and len(azure.commandes) == 2 and len(pauses) == 1


@pytest.mark.parametrize(
    "erreur",
    [
        "(AuthorizationFailed) 403 Forbidden",
        "401 Unauthorized",
        "(InvalidRequestContent) YAML invalide",
        "(ContainerAppImageNotFound) image absente",
    ],
)
def test_erreur_definitive_echoue_sans_nouvelle_tentative(erreur: str) -> None:
    azure = Azure((3, erreur))
    assert lancer(azure, ["az", "x"]) == (3, [])


def test_tentatives_bornees_rend_le_dernier_code() -> None:
    azure = Azure(*[(1, "Service Unavailable")] * TENTATIVES)
    code, pauses = lancer(azure, ["az", "x"])
    assert code == 1 and len(azure.commandes) == TENTATIVES and len(pauses) == TENTATIVES - 1


def _app(image: str, deploiement: str = "") -> str:
    env = [{"name": "DEPLOIEMENT", "value": deploiement}] if deploiement else []
    return json.dumps({"properties": {"template": {"containers": [{"image": image, "env": env}]}}})


def _yaml(tmp_path: Path, image: str, deploiement: str = "") -> str:
    env = f'env:\n  - {{ name: DEPLOIEMENT, value: "{deploiement}" }}\n' if deploiement else ""
    fichier = tmp_path / "app.yaml"
    fichier.write_text(f"containers:\n  - name: a\n    image: {image}\n{env}", encoding="utf-8")
    return str(fichier)


def test_server_timeout_deja_applique_ne_rejoue_pas(tmp_path: Path) -> None:
    azure = Azure((1, "(ServerTimeout) The request timed out"), (0, _app("img:abc")))
    code, pauses = lancer(azure, [*UPDATE, _yaml(tmp_path, "img:abc")])
    assert (code, pauses) == (0, [])
    assert azure.commandes[1][:3] == ["az", "containerapp", "show"]


def test_server_timeout_non_applique_rejoue(tmp_path: Path) -> None:
    azure = Azure((1, "(ServerTimeout)"), (0, _app("img:ancienne")), (0, "ok"))
    code, _ = lancer(azure, [*UPDATE, _yaml(tmp_path, "img:abc")])
    assert code == 0 and azure.commandes[2][:3] == ["az", "containerapp", "update"]


def test_meme_image_mais_autre_deploiement_postgres_rejoue(tmp_path: Path) -> None:
    # l'image de PostgreSQL ne change pas : seul DEPLOIEMENT dit que la base a été recréée
    azure = Azure((1, "(ServerTimeout)"), (0, _app("pg:3", "ancien")), (0, "ok"))
    code, _ = lancer(azure, [*UPDATE, _yaml(tmp_path, "pg:3", "nouveau")])
    assert code == 0 and len(azure.commandes) == 3


def test_le_workflow_passe_tous_ses_appels_azure_d_ecriture_par_le_rejeu() -> None:
    lignes = WORKFLOW.read_text(encoding="utf-8").splitlines()
    ecritures = [
        ligne.strip()
        for ligne in lignes
        if re.search(
            r"az (containerapp update|functionapp (config appsettings set|deployment))", ligne
        )
    ]
    assert len(ecritures) == 8
    assert all(e.startswith("python3 tools/az_reessayer.py az ") for e in ecritures), ecritures
