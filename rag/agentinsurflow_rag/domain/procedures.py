"""Procédures internes : fusion de l'instantané du barème et des textes rédigés (#99).

Le barème fournit la condition, le motif et l'effet ; le rédigé fournit le reste (pièces,
fondement, décision, information). Aucune dépendance hors bibliothèque standard.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

OPERATEURS = {">=": "au moins", ">": "plus de", "<": "moins de"}
MARQUEUR = re.compile(r"\{[^{}]*\}")


class ErreurProcedures(ValueError):
    """Le barème et les procédures rédigées ne se correspondent pas."""


def condition_lisible(conditions: Sequence[Mapping[str, str]]) -> str:
    return " et ".join(
        f"`{c['champ']}` {OPERATEURS[c['operateur']]} {c['seuil'].replace('.', ',')}"
        for c in conditions
    )


def generer(
    bareme: Mapping[str, Any], rediges: Mapping[str, str], url_depot: str
) -> list[dict[str, Any]]:
    """Une procédure par règle du barème, dans l'ordre du barème."""
    manifeste = bareme["manifeste"]
    version_bareme = manifeste["version_bareme"]
    ids = [r["regle_id"] for r in bareme["regles"]]
    sans_regle = sorted(set(rediges) - set(ids))
    if sans_regle:
        raise ErreurProcedures(f"procédure rédigée sans règle au barème : {', '.join(sans_regle)}")
    documents = []
    for regle in bareme["regles"]:
        regle_id = regle["regle_id"]
        if regle_id not in rediges:
            raise ErreurProcedures(f"{regle_id} : aucune procédure rédigée")
        corps = rediges[regle_id].replace("{version_bareme}", version_bareme)
        if MARQUEUR.search(corps):
            raise ErreurProcedures(f"{regle_id} : marqueur inconnu dans la procédure rédigée")
        texte = (
            f"# Procédure interne {regle_id} — {regle['libelle']}\n\n"
            "Document fictif rédigé pour le projet AgentInsurFlow.\n\n"
            "## Règle\n"
            f"Condition : {condition_lisible(regle['conditions'])}.\n"
            f"Motif retenu par le barème : « {regle['motif']} »\n"
            f"Effet : {regle['effet']} (barème {version_bareme}).\n\n"
            f"{corps}"
        )
        documents.append(
            {
                "doc_id": f"PI-{regle_id}",
                "version": f"PI-{regle_id}-{version_bareme}",
                "article": f"PI-{regle_id.replace('_', '-')}",
                "date_debut": manifeste["date_debut"],
                "etat": "VIGUEUR",
                "regle_id": regle_id,
                "texte_html": texte,
                "url_source": f"{url_depot}/procedures_internes/{regle_id}.md",
            }
        )
    return documents
