"""Règles déterministes d'injection de prompt (FR/EN), stdlib seulement.

Le texte est normalisé (NFKD, sans accents, minuscules) puis confronté à des motifs nommés.
Le modèle PromptInjection de LLM Guard n'est qu'un signal : ce sont ces règles qui bloquent.
"""

from __future__ import annotations

import re
import unicodedata

_CIBLE = (
    r"(?:consignes?|instructions?|regles?|directives?|baremes?|garde-?fous?|guidelines?|rules?|"
    r"prompts?|restrictions?|refus|refusal|rejection)"
)
_VERBE_OUTRE = (
    r"(?:ignore[rz]?|oublie[rz]?|neglige[rz]?|contourne[rz]?|ne tiens? pas compte|"
    r"ne tenez pas compte|disregard|forget|override|bypass)"
)

# nom : (description en une ligne, motif sur texte normalisé)
MOTIFS: dict[str, tuple[str, re.Pattern[str]]] = {
    nom: (doc, re.compile(motif, re.S))
    for nom, (doc, motif) in {
        "passer_outre": (
            "ordre d'ignorer/oublier/contourner consignes, règles, barème ou refus (FR/EN)",
            rf"\b{_VERBE_OUTRE}\b.{{0,40}}\b{_CIBLE}\b",
        ),
        "changement_de_role": (
            "changement de rôle : « tu es maintenant », « à partir de maintenant », « act as »",
            r"\b(?:tu es maintenant|tu n'es plus|a partir de maintenant|desormais,? "
            r"(?:reponds|tu|ignore|accepte|valide)|agis comme|fais comme si|you are now|"
            r"act as|pretend (?:to be|you))\b",
        ),
        "prompt_systeme": (
            "demande du prompt système ou de ses instructions (révèle, affiche, répète…)",
            r"\b(?:prompt systeme|system prompt|instruction systeme|mot pour mot)\b|"
            r"\b(?:revele[rz]?|affiche[rz]?|montre[rz]?|repete[rz]?|print|reveal|show|display|"
            r"repeat)\b.{0,30}\b(?:tes|vos|your)\s+(?:instructions|consignes|prompt)",
        ),
        "ordre_de_decider": (
            "ordre d'accepter/valider/approuver le dossier ou décision imposée (FR/EN)",
            r"\b(?:accepte[rz]?|valide[rz]?|approuve[rz]?|approve)\b.{0,25}\b(?:ce|cet|le|this|the)"
            r"\s+(?:dossier|contrat|file|application|contract)\b|\bjust (?:confirm|approve)\b|"
            r"\bdecision\s+accepte\b|\boutput decision\b",
        ),
        "ordre_de_statut": (
            "ordre de fixer prime, statut ou score, ou ordre sans vérification",
            r"\b(?:mets|met|passe|fixe|set)\b.{0,25}\b(?:prime|statut|score|decision|status|"
            r"premium)\b.{0,15}\b(?:a|au|en|to|at)\b|\bc'est un ordre\b|"
            r"\bsans (?:aucune )?verification\b",
        ),
        "balise_evasion": (
            "balises d'évasion : fermeture de <donnees_non_fiables>, ### system, [INST], [SYSTÈME]",
            r"</?donnees_non_fiables>|###\s*system|\[/?inst\]|\[/?systeme?\]|\bmode "
            r"(?:maintenance|developpeur|debug|admin)\b",
        ),
        "nouvelle_instruction": (
            "annonce d'une « nouvelle instruction/consigne » (FR/EN : new system prompt)",
            r"\bnouvell?es? (?:instruction|consigne|directive)s?\b|\bnew (?:system )?"
            r"(?:instructions?|prompt)\b",
        ),
        "donnees_identite": (
            "demande du nom, adresse, permis, IBAN… du souscripteur",
            r"\b(?:donne|communique|fournis|affiche|revele|liste|give|tell)(?:-moi)?\b.{0,30}\b"
            r"(?:nom|adresse|numero|iban|telephone|mail|email|naissance|permis)\b.{0,30}\b"
            r"(?:souscripteur|assure|client|conducteur|titulaire|policyholder|customer)",
        ),
        "autres_dossiers": (
            "demande de données d'autres dossiers, clients ou contrats",
            r"\bautres? (?:dossiers?|clients?|contrats?)\b|\bother (?:files|customers|clients)\b",
        ),
        "secrets": (
            "demande de clés, jetons, mots de passe ou variables d'environnement",
            r"\b(?:donne|liste|affiche|revele|montre|print|show|give)[rz]?\b.{0,40}\b(?:cles? "
            r"d'api|api keys?|jetons?|tokens?|mots? de passe|variables? d'environnement|"
            r"credentials)\b|\bcredentials\b",
        ),
    }.items()
}


def _normaliser(texte: str) -> str:
    decompose = unicodedata.normalize("NFKD", texte.replace("’", "'"))
    return "".join(c for c in decompose if not unicodedata.combining(c)).casefold()


def motifs_injection(texte: str) -> list[str]:
    """Noms des motifs d'injection reconnus dans `texte` (liste vide = rien de suspect)."""
    normalise = _normaliser(texte)
    return [nom for nom, (_, motif) in MOTIFS.items() if motif.search(normalise)]
