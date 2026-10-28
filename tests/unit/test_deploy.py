"""deploy.yml : l'ingestion du corpus obtient son jeton juste après une connexion Azure fraîche."""

from pathlib import Path

import yaml

RACINE = Path(__file__).resolve().parents[2]


def test_reconnexion_azure_juste_avant_l_ingestion():
    # l'assertion OIDC de GitHub expire en quelques minutes : un job plus long que ça
    # (production, 13 min le 28/10) ne peut plus demander de jeton pour api://agentinsurflow-rag
    deploy = yaml.safe_load((RACINE / ".github/workflows/deploy.yml").read_text())
    etapes = deploy["jobs"]["deploy"]["steps"]
    i = next(n for n, e in enumerate(etapes) if e.get("name", "").startswith("Corpus"))
    assert etapes[i - 1].get("uses", "").startswith("azure/login@"), etapes[i - 1]
    assert etapes[i - 1]["with"] == etapes[0]["with"]
