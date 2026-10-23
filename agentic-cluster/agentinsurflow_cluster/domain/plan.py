"""Plan de référence (dossier p. 16–17) : prochaine étape et préconditions GO2, fonctions pures."""

from __future__ import annotations

from typing import Literal

from agentinsurflow_cluster.domain.models import EtatDossier

Appel = Literal[
    "appeler_pieces",
    "appeler_analyste_risque",
    "appeler_redacteur",
    "appeler_actuaire",
    "proposer_au_gestionnaire",
    "orienter_revue_humaine",
]


def prochaine_etape(etat: EtatDossier) -> tuple[Appel, str | None]:
    """Renvoie (appel, cause). La cause n'est renseignée que pour la revue humaine."""
    if etat.cause:  # un agent est déjà tombé en revue humaine : il l'emporte
        return "orienter_revue_humaine", etat.cause
    if etat.pieces is None:
        return "appeler_pieces", None
    # R2 : entrée bloquée => on enchaîne jusqu'au risque quel que soit le statut des pièces.
    if etat.risque is None and (etat.entree_bloquee or etat.pieces.statut == "complet"):
        return "appeler_analyste_risque", None
    if etat.entree_bloquee:
        return "orienter_revue_humaine", etat.entree_bloquee
    if etat.pieces.statut == "incomplet":  # 7a ; remplacé par demander_complement en 7b
        return "orienter_revue_humaine", "pieces_incompletes"
    if etat.risque is not None and etat.risque.classe == "limite":
        return "orienter_revue_humaine", "limite"
    if etat.fiche is None:
        return "appeler_redacteur", None
    if etat.fiche.decision == "ACCEPTE" and etat.prime is None:
        return "appeler_actuaire", None
    if etat.fiche.decision in ("ACCEPTE", "REFUSE"):
        return "proposer_au_gestionnaire", None
    return "orienter_revue_humaine", "fiche_revue_humaine"


def precondition(appel: Appel, etat: EtatDossier) -> str | None:
    """GO2 : None si l'appel est autorisé, sinon la raison du refus."""
    match appel:
        case "appeler_pieces":
            if etat.dossier is None:
                return "dossier non chargé"
            return "déjà fait" if etat.pieces is not None else None
        case "appeler_analyste_risque":
            if etat.risque is not None:
                return "déjà fait"
            # R2 : entrée bloquée => exigence « pièces complètes » levée (pièces requises).
            ok = etat.pieces is not None and (
                etat.pieces.statut == "complet" or bool(etat.entree_bloquee)
            )
            return None if ok else "pièces incomplètes"
        case "appeler_redacteur":
            if etat.fiche is not None:
                return "déjà fait"
            if etat.risque is None:
                return "risque absent"
            return None if etat.risque.classe in ("acceptable", "refus") else "classe limite"
        case "appeler_actuaire":
            ok = etat.fiche is not None and etat.fiche.decision == "ACCEPTE" and etat.prime is None
            return None if ok else "pas de prime sans ACCEPTE"
        case "proposer_au_gestionnaire":
            f = etat.fiche
            ok = f is not None and (
                f.decision == "REFUSE" or (f.decision == "ACCEPTE" and etat.prime is not None)
            )
            return None if ok else "fiche ou prime absente"
        case "orienter_revue_humaine":
            return None
