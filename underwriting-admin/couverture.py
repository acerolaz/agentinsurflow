"""Couverture de lignes d'underwriting-admin, tous projets de test confondus (TU + TI).

Chaque projet de test mesure ses propres assemblies : un seuil par projet pénaliserait le Domain (testé par
Domain.Tests) parce qu'Application.Tests le charge sans l'exercer. On fusionne donc les rapports Cobertura
(une ligne est couverte si un projet au moins la couvre) et on applique le seuil au total.

Usage : python3 couverture.py <dossier des rapports> <seuil en %>
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def fusionner(dossier: Path) -> dict[tuple[str, int], int]:
    lignes: dict[tuple[str, int], int] = {}
    for rapport in dossier.glob("*.xml"):
        for classe in ET.parse(rapport).getroot().iter("class"):
            fichier = classe.get("filename", "")
            for ligne in classe.iter("line"):
                cle = (fichier, int(ligne.get("number", "0")))
                lignes[cle] = max(lignes.get(cle, 0), int(ligne.get("hits", "0")))
    return lignes


if __name__ == "__main__":
    lignes = fusionner(Path(sys.argv[1]))
    seuil = float(sys.argv[2])
    couvertes = sum(1 for hits in lignes.values() if hits > 0)
    pourcentage = 100 * couvertes / len(lignes) if lignes else 0.0
    print(f"Couverture de lignes (tous projets de test) : {pourcentage:.1f} % ({couvertes}/{len(lignes)}), seuil {seuil:.0f} %")
    sys.exit(0 if pourcentage >= seuil else 1)
