"""Attribution Etalab 2.0 : mentions dues au réutilisateur des données Légifrance (DILA)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

SOURCE = "Légifrance"
CONCEDANT = "Direction de l'information légale et administrative (DILA)"
LICENCE_NOM = "Licence Ouverte / Open Licence version 2.0"
LICENCE_URL = "https://www.etalab.gouv.fr/licence-ouverte-open-licence/"
MODIFICATIONS = (
    "Texte retraité par AgentInsurFlow : balises HTML retirées, texte normalisé et découpé "
    "en extraits. Le texte original est consultable via url_source."
)


class VersionIntrouvable(Exception):
    """La version demandée (ou, à défaut, la version courante) n'existe pas pour cet article."""


@dataclass(frozen=True)
class Attribution:
    doc_id: str
    article: str
    version: str
    date_debut: date | None
    url_source: str
    mise_a_jour_le: date
    source: str = SOURCE
    concedant: str = CONCEDANT
    licence_nom: str = LICENCE_NOM
    licence_url: str = LICENCE_URL
    modifications: str = MODIFICATIONS
