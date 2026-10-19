"""Lecture d'un dossier pour l'agent : la vue minimisée, ou une erreur explicite.

Le contrôle BOLA est fait par underwriting-admin (jeton OBO du gestionnaire) : un contrat absent
et un contrat d'un autre gestionnaire donnent la même erreur.
"""

from __future__ import annotations

from ...domain.models import VueContrat
from ...domain.ports import ContratIntrouvable, DepotDossiers, ErreurDossiers


async def consulter_contrat(dossiers: DepotDossiers | None, numero_contrat: str) -> VueContrat:
    if dossiers is None:
        raise ErreurDossiers("accès aux dossiers non configuré")
    contrat = await dossiers.lire_contrat(numero_contrat)
    if contrat is None:
        raise ContratIntrouvable(numero_contrat)
    return contrat
