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


def _etapes():
    deploy = yaml.safe_load((RACINE / ".github/workflows/deploy.yml").read_text())
    return deploy["jobs"]["deploy"]["steps"]


def _indice(etapes, debut):
    return next(n for n, e in enumerate(etapes) if e.get("name", "").startswith(debut))


def test_base_annexe_demarre_pendant_la_function_et_precede_ses_clients():
    # la Function (≈ 2 min) recouvre le démarrage de la base ; ses clients migrent sur la base neuve
    e = _etapes()
    assert (
        _indice(e, "Lancer la base annexe")
        < _indice(e, "Déployer la Function")
        < _indice(e, "Base annexe prête")
        < _indice(e, "Déployer underwriting-admin")
    )


def test_apps_lancees_sans_attendre_puis_attendues_ensemble():
    # 7 updates en série coûtaient ≈ 5 min chacun en staging (32 min, run 40734064386)
    e = _etapes()
    updates = [x["run"] for x in e if "az containerapp update" in x.get("run", "")]
    assert len(updates) == 6 and all("--no-wait" in r for r in updates)
    attente = _indice(e, "Révisions prêtes")
    for app in (
        "Déployer underwriting-admin",
        "Déployer le serveur MCP",
        "Déployer le cluster",
        "Déployer la gateway",
        "Déployer rag",
    ):
        assert _indice(e, app) < attente, app
    assert attente < _indice(e, "Identité managée conservée") < _indice(e, "Fumée par la gateway")


def test_chaque_run_cree_une_revision_de_la_base_et_de_ses_clients():
    # #186 : redéployer le même SHA doit recréer la base vide, rejouer les migrations et réingérer
    # le corpus ; un modèle identique ne crée aucune révision, d'où une valeur propre au run
    for fichier in ("postgres", "rag", "underwriting"):
        modele = yaml.safe_load((RACINE / f"infra/containerapp-{fichier}.yaml").read_text())
        env = modele["properties"]["template"]["containers"][0]["env"]
        assert {"name": "DEPLOIEMENT", "value": "${DEPLOIEMENT}"} in env, fichier
    e = _etapes()
    for debut in ("Lancer la base annexe", "Déployer underwriting-admin", "Déployer rag"):
        etape = e[_indice(e, debut)]
        assert etape["env"]["DEPLOIEMENT"] == "${{ github.run_id }}-${{ github.run_attempt }}"
        assert "$DEPLOIEMENT" in etape["run"], debut
