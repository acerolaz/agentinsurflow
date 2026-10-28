"""`python -m entrainement` : entraîne, évalue, écrit l'artefact, la fiche et rapport-modele.md.

Sans `seuils.toml`, ou avec `--init-seuils`, la mesure fixe le seuil (D² - 0,005) ; sinon la porte
de qualité s'applique et le code de sortie est 1 si elle échoue.
"""

import argparse
import datetime
import json
import os
import subprocess
import sys
import time
import tomllib
from pathlib import Path

from entrainement import donnees, modele

RACINE = Path(__file__).resolve().parent.parent
SEUILS = Path(__file__).parent / "seuils.toml"
MODELES = RACINE / "agentinsurflow_calcul" / "modeles"
MARGE = 0.005


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--cache", type=Path, default=Path(os.environ.get("FREMTPL2_CACHE", "/tmp/fremtpl2-cache"))
    )
    p.add_argument("--init-seuils", action="store_true", help="écrit seuils.toml depuis la mesure")
    p.add_argument("--rapport", type=Path, default=RACINE.parent / "rapport-modele.md")
    args = p.parse_args()

    debut = time.monotonic()
    args.cache.mkdir(parents=True, exist_ok=True)
    df = donnees.preparer(donnees.charger(donnees.telecharger(args.cache)))
    train, test = donnees.separer(df)
    m = modele.entrainer(train)
    metriques = modele.evaluer(m, test, train)
    duree = time.monotonic() - debut

    jour = datetime.date.today()
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    source = tomllib.loads((Path(donnees.__file__).parent / "donnees.toml").read_text("utf-8"))[
        "source"
    ]
    version = f"glm-freq-{jour:%Y%m%d}-v1"
    artefact = modele.exporter(
        m, metriques, source, version, commit=commit, entraine_le=jour.isoformat()
    )

    if metriques["d2"] <= 0 or metriques["deviance_moyenne"] >= metriques["deviance_moyenne_nul"]:
        print(f"BLOQUÉ : le modèle ne bat pas le modèle nul : {metriques}", file=sys.stderr)
        return 2
    if args.init_seuils or not SEUILS.exists():
        SEUILS.write_text(
            f"# Porte de qualité du GLM de fréquence : seuil = mesure - marge, jamais inventé.\n"
            f"d2_min = {metriques['d2'] - MARGE:.6f}\n"
            f"d2_mesure = {metriques['d2']:.6f}\n"
            f'mesure_le = "{jour.isoformat()}"\n'
            f'commit = "{commit}"\n',
            encoding="utf-8",
        )
    seuils = tomllib.loads(SEUILS.read_text("utf-8"))
    raisons = modele.porte(metriques, seuils)

    MODELES.mkdir(exist_ok=True)
    (MODELES / f"{version}.json").write_text(
        json.dumps(artefact, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (MODELES / f"{version}.md").write_text(modele.fiche(artefact, seuils), encoding="utf-8")
    args.rapport.write_text(
        f"# Rapport d'entraînement {version}\n\n"
        f"- durée : {duree:.1f} s\n- D² : {metriques['d2']:.6f} (seuil {seuils['d2_min']:.6f})\n"
        f"- Gini : {metriques['gini']:.6f}\n- porte : {'OK' if not raisons else raisons}\n",
        encoding="utf-8",
    )
    print(f"{version} : D² {metriques['d2']:.6f}, Gini {metriques['gini']:.6f}, {duree:.1f} s")
    for r in raisons:
        print(f"PORTE REFUSÉE : {r}", file=sys.stderr)
    return 1 if raisons else 0


if __name__ == "__main__":
    sys.exit(main())
