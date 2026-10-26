"""Règles du corpus (spec §3.2 et §4.1) : nettoyage, dédup, découpage, références, porte.

Fonctions pures, bibliothèque standard seulement : elles se testent sans base ni modèle.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Mapping
from datetime import date
from html.parser import HTMLParser
from typing import Literal

from .models import ArticlePropre, Rejet

TEXTE_MIN = 20  # caractères
ETATS_RETENUS = frozenset({"VIGUEUR"})  # 🔴 à confirmer au premier appel Légifrance (Task G0)
CHAMPS_OBLIGATOIRES = ("doc_id", "version", "article", "etat", "texte_html", "url_source")
CARACTERES_PAR_TOKEN = (
    4  # ponytail: tokens ≈ caractères ÷ 4 ; tiktoken si le découpage doit être exact
)

_REFERENCE = re.compile(r"(?<![A-Za-z0-9])([LRAD])\s*\.?\s*(\d+(?:-\d+)+)", re.IGNORECASE)
_BLOCS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "table", "ul", "ol"}

Decision = Literal["nouveau", "inchange", "nouvelle_version", "conflit_version"]

COLLECTION_S3 = "textes_reglementaires"
COLLECTION_NOTICES = "notices_produits"
COLLECTION_PROCEDURES = "procedures_internes"
# Refus par défaut : un rôle absent de la table ne lit aucune collection (spec §4.1)
COLLECTIONS_PAR_ROLE: dict[str, tuple[str, ...]] = {
    "Gestionnaire": (COLLECTION_S3, COLLECTION_NOTICES, COLLECTION_PROCEDURES)
}


def collections_pour(roles: frozenset[str]) -> list[str]:
    """Collections lisibles par un appelant, dans un ordre stable, sans doublon."""
    return sorted({c for role in roles for c in COLLECTIONS_PAR_ROLE.get(role, ())})


def normaliser_numero(numero: str) -> str:
    """« L. 211-1 » → « L211-1 » : majuscules, sans espace ni point."""
    return re.sub(r"[\s.]", "", numero).upper()


def references_articles(question: str) -> list[str]:
    """Numéros d'articles cités dans la question, normalisés, sans doublon, dans l'ordre."""
    return list(
        dict.fromkeys(
            normaliser_numero(lettre + num) for lettre, num in _REFERENCE.findall(question)
        )
    )


class _Texte(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.morceaux: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.morceaux.append("\n" if tag in _BLOCS else " " if tag in {"td", "th"} else "")

    def handle_endtag(self, tag: str) -> None:
        self.handle_starttag(tag, [])

    def handle_data(self, data: str) -> None:
        self.morceaux.append(data)


def html_vers_texte(html: str) -> str:
    """HTML Légifrance → texte : balises retirées, NFC, espaces fusionnés, un bloc par ligne."""
    lecteur = _Texte()
    lecteur.feed(html)
    lecteur.close()
    brut = unicodedata.normalize("NFC", "".join(lecteur.morceaux))
    lignes = (" ".join(ligne.split()) for ligne in brut.split("\n"))
    return "\n".join(ligne for ligne in lignes if ligne)


def hash_contenu(texte: str) -> str:
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


def _date(valeur: object) -> date | None:
    if valeur in (None, ""):
        return None
    return date.fromisoformat(str(valeur)[:10])


def nettoyer(brut: Mapping[str, object]) -> ArticlePropre | Rejet:
    """Article brut du lot → article propre, ou rejet avec sa raison (C3 : sans bloquer le lot)."""
    doc_id = brut.get("doc_id")
    identifiant = doc_id if isinstance(doc_id, str) and doc_id.strip() else None
    for champ in CHAMPS_OBLIGATOIRES:
        valeur = brut.get(champ)
        if not isinstance(valeur, str) or not valeur.strip():
            return Rejet(identifiant, f"partiel:{champ}")
    texte = html_vers_texte(str(brut["texte_html"]))
    if not texte:
        return Rejet(identifiant, "vide")
    if len(texte) < TEXTE_MIN:
        return Rejet(identifiant, "trop_court")
    etat = str(brut["etat"]).strip()
    if etat not in ETATS_RETENUS:
        return Rejet(identifiant, f"non_en_vigueur:{etat}")
    try:
        date_debut = _date(brut.get("date_debut"))
    except ValueError:
        return Rejet(identifiant, "date_invalide")
    regle = brut.get("regle_id")
    regle_id = regle.strip() if isinstance(regle, str) and regle.strip() else None
    # le hash couvre la règle : la changer sous la même version est un conflit, pas un « inchangé »
    empreinte = texte if regle_id is None else f"{texte}\n{regle_id}"
    return ArticlePropre(
        doc_id=str(identifiant),
        version=str(brut["version"]).strip(),
        article=normaliser_numero(str(brut["article"])),
        date_debut=date_debut,
        etat=etat,
        url_source=str(brut["url_source"]).strip(),
        texte=texte,
        hash_contenu=hash_contenu(empreinte),
        regle_id=regle_id,
    )


def decider(courant: tuple[str, str] | None, version: str, hash_: str) -> Decision:
    """Dédup (S3-9) : ``courant`` = (version, hash) de la version non obsolète du même ``doc_id``.

    Même contenu → inchangé ; contenu et version nouveaux → nouvelle version (l'ancienne devient
    obsolète) ; contenu modifié sous la même version → conflit, signalé au lieu d'écraser.
    """
    if courant is None:
        return "nouveau"
    version_courante, hash_courant = courant
    if hash_ == hash_courant:
        return "inchange"
    return "conflit_version" if version == version_courante else "nouvelle_version"


def decouper(texte: str, max_tokens: int = 500, recouvrement: int = 50) -> list[str]:
    """1 article = 1 chunk ; au-delà, redécoupage par paragraphes, avec un recouvrement.

    Chaque chunk fait au plus ``max_tokens`` × 4 caractères ; le suivant commence par les
    ``recouvrement`` × 4 derniers caractères du précédent.
    """
    limite = max_tokens * CARACTERES_PAR_TOKEN
    if len(texte) <= limite:
        return [texte]
    queue = recouvrement * CARACTERES_PAR_TOKEN
    taille = limite - queue - 1  # un morceau + la queue du chunk précédent + "\n" tiennent
    morceaux = [
        paragraphe[i : i + taille]
        for paragraphe in texte.split("\n")
        for i in range(0, max(len(paragraphe), 1), taille)
    ]
    chunks: list[str] = []
    courant = ""
    for morceau in morceaux:
        candidat = f"{courant}\n{morceau}" if courant else morceau
        if len(candidat) <= limite:
            courant = candidat
            continue
        chunks.append(courant)
        courant = f"{courant[-queue:]}\n{morceau}"
    chunks.append(courant)
    return chunks


def passe_la_porte(cosinus_max: float | None, reference_trouvee: bool, seuil: float) -> bool:
    """Porte de pertinence (§4.1) : cosinus max ≥ seuil, ou référence exacte à un article."""
    return reference_trouvee or (cosinus_max is not None and cosinus_max >= seuil)
