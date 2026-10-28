"""ci-cd.yml / deploy.yml : le modèle de fréquence ne part en staging que si sa porte passe (C13).

Niveau : TU (lecture des workflows YAML, aucune I/O réseau).
"""

import json
import math
import textwrap
from pathlib import Path

import yaml

RACINE = Path(__file__).resolve().parents[2]
CI = yaml.safe_load((RACINE / ".github/workflows/ci-cd.yml").read_text())
DEPLOY = (RACINE / ".github/workflows/deploy.yml").read_text()
MODELE = CI["jobs"]["modele"]


def _scripts() -> str:
    return "\n".join(e.get("run", "") for e in MODELE["steps"])


def test_job_modele_filtre_ses_chemins():
    diff = next(e for e in MODELE["steps"] if e.get("id") == "diff")
    assert "git diff --name-only" in diff["run"]
    motif = diff["env"]["DECLENCHEURS_MODELE"]
    for chemin in (
        "entrainement/",  # contient donnees.toml et seuils.toml
        r"domain/frequence\.py",
        r"domain/regions\.py",
        "modeles/",
    ):
        assert chemin in motif, chemin
    assert any("steps.diff.outputs" in str(e.get("if", "")) for e in MODELE["steps"])


def test_staging_attend_la_porte_du_modele():
    staging = CI["jobs"]["staging"]
    assert "modele" in staging["needs"]
    cond = staging["if"]
    # passé ou sauté = autorisé ; échoué, annulé ou expiré = bloquant ;
    # un build non réussi bloque toujours
    assert "(needs.modele.result == 'success' || needs.modele.result == 'skipped')" in cond
    assert "needs.build.result == 'success'" in cond
    assert "!cancelled()" in cond


def test_donnees_en_cache_par_sha():
    caches = [e for e in MODELE["steps"] if str(e.get("uses", "")).startswith("actions/cache@")]
    assert len(caches) == 1
    cle = caches[0]["with"]["key"]
    assert "hashFiles('fonction-calcul/entrainement/donnees.toml')" in cle


def test_rapport_joint_au_run():
    ups = [
        e for e in MODELE["steps"] if str(e.get("uses", "")).startswith("actions/upload-artifact@")
    ]
    assert ups and "rapport-modele.md" in ups[0]["with"]["path"]
    assert ups[0]["if"] == "always() && steps.diff.outputs.actif == 'true'"


def test_artefact_compare_hors_commit_et_date():
    script = _scripts()
    assert "make modele" in script
    assert "entraine_le" in script and "commit" in script
    assert "réentraîné ≠ commité : commiter le nouvel artefact" in script


def _bruite(d, r):
    if isinstance(d, dict):
        return {k: _bruite(v, r) for k, v in d.items()}
    if isinstance(d, list):
        return [_bruite(v, r) for v in d]
    return d * (1 + r) if isinstance(d, float) and d else d


def test_artefact_tolere_le_bruit_blas_pas_un_autre_modele():
    """Écart macOS/Linux mesuré le 28/10 : ≤ 6e-5 relatif ; un décalage de 1 % reste refusé."""
    script = _scripts()
    ns = {"math": math}
    exec(textwrap.dedent(script[script.index("def proche") : script.index("def charge")]), ns)
    artefact = next((RACINE / "fonction-calcul/agentinsurflow_calcul/modeles").glob("*.json"))
    base = json.loads(artefact.read_text())
    assert ns["proche"](base, _bruite(base, 6e-5))
    assert not ns["proche"](base, _bruite(base, 1e-2))


def test_fumee_frequence_fermee_sans_jeton():
    assert "$URL/api/calcul/frequence" in DEPLOY
    assert "POST /api/calcul/frequence sans jeton" in DEPLOY
