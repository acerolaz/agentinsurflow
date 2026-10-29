"""ci-cd.yml : le job evals-pr évalue l'API de staging sur les PR et commente le résumé (C13, #55).

Niveau : TU (lecture du workflow YAML, aucune I/O réseau).
"""

from pathlib import Path

import yaml

RACINE = Path(__file__).resolve().parents[2]
CI = yaml.safe_load((RACINE / ".github/workflows/ci-cd.yml").read_text())
JOB = CI["jobs"]["evals-pr"]
ON = CI[True]  # PyYAML lit `on:` comme True


def _etape(motif: str) -> int:
    """Indice de la première étape dont le uses/run/name contient le motif."""
    for i, e in enumerate(JOB["steps"]):
        if motif in f"{e.get('uses', '')}\n{e.get('run', '')}\n{e.get('name', '')}":
            return i
    raise AssertionError(f"aucune étape pour {motif!r}")


def test_declencheurs_libelle_et_manuel():
    assert "labeled" in ON["pull_request"]["types"] and "workflow_dispatch" in ON


def test_evals_pr_reactive_et_forcable():
    assert "false" not in JOB["if"]
    for morceau in ("needs.changements.outputs.evals", "workflow_dispatch", "'evals'"):
        assert morceau in JOB["if"]


def test_seul_evals_pr_ecrit_sur_les_pr():
    assert JOB["permissions"]["pull-requests"] == "write"
    assert all(
        "pull-requests" not in (j.get("permissions") or {})
        for n, j in CI["jobs"].items()
        if n != "evals-pr"
    )


def test_donnees_testees_avant_toute_connexion():
    assert _etape("make donnees-evals") < _etape("azure/login")


def test_staging_url_exigee():
    assert "vars.STAGING_URL" in str(JOB)
    controle = JOB["steps"][_etape("::error::")]["run"]
    assert "STAGING_URL" in controle and "exit 1" in controle


def test_evaluation_contre_staging_avec_resume():
    run = JOB["steps"][_etape("tools/evals.py")]["run"]
    for morceau in ('--url "$STAGING_URL"', "--rapport evals-pr.json", "--resume evals-pr.md"):
        assert morceau in run


def test_commentaire_meme_sans_rapport():
    etape = JOB["steps"][_etape("--edit-last")]
    assert etape["if"] == "${{ !cancelled() }}"  # run annulé: pas de faux rapport absent
    assert "rapport absent" in etape["run"]
    assert "--edit-last --create-if-none" in etape["run"]
    assert "GITHUB_STEP_SUMMARY" in etape["run"]
    assert etape["env"]["GH_TOKEN"] == "${{ github.token }}"


def test_jeton_masque():
    run = JOB["steps"][_etape("tools/evals.py")]["run"]
    assert run.index("::add-mask::") < run.index("export EVALS_JETON")


def test_chaine_de_merge_fermee_aux_nouveaux_evenements():
    for nom in ("build",):
        assert CI["jobs"][nom]["if"] == "github.event_name == 'push'"
    jobs = CI["jobs"]
    assert "build" in jobs["staging"]["needs"]
    assert "staging" in jobs["release"]["needs"]
    assert "release" in jobs["production"]["needs"]
