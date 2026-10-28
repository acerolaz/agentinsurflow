"""D26 retirée (S4) : plus de saver PostgreSQL au cluster, rôle PointsDeReprise à lui seul."""

import re
import subprocess
from pathlib import Path

import yaml

RACINE = Path(__file__).resolve().parents[2]
MOTIFS = (
    "INSURFLOW_CHECKPOINT_DSN",
    "checkpoint-dsn",
    "agent_state",
    "agent-state",
    "AGENT_STATE",
    "langgraph-checkpoint-postgres",
)
# Doc et historique : traités à part (README à la Task 6)
EXCLUS = (".superpowers/", "docs/", "uv.lock")


def _fichiers_suivis() -> list[Path]:
    sortie = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=RACINE,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    return [
        RACINE / f
        for f in sortie
        if not f.startswith(EXCLUS)
        and not f.endswith(".md")
        and f != "tests/unit/test_d26_retire.py"
        and (RACINE / f).is_file()
    ]


def test_plus_aucune_reference_d26():
    restes = []
    for fichier in _fichiers_suivis():
        try:
            texte = fichier.read_text()
        except UnicodeDecodeError:
            continue
        restes += [f"{fichier.relative_to(RACINE)}: {m}" for m in MOTIFS if m in texte]
    assert restes == []


def test_role_points_de_reprise_attribue_au_seul_cluster():
    lignes = [
        ligne
        for ligne in (RACINE / "infra/entra.sh").read_text().splitlines()
        if re.match(r"\s*attribuer\b.*UW_POINTS_DE_REPRISE", ligne)
    ]
    assert len(lignes) == 1
    assert '--id "$cluster"' in lignes[0]


def test_compose_donne_le_mot_de_passe_points_reprise_a_underwriting_admin():
    compose = yaml.safe_load((RACINE / "docker-compose.yml").read_text())
    env = compose["services"]["underwriting-admin"]["environment"]
    assert "PG_POINTS_REPRISE_PASSWORD" in env
