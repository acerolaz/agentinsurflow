"""Règles déterministes d'injection de prompt (FR/EN), stdlib seulement.

Le texte est normalisé (NFKD, sans accents, minuscules) puis confronté à des motifs nommés.
Le modèle PromptInjection de LLM Guard n'est qu'un signal : ce sont ces règles qui bloquent.
"""

from __future__ import annotations

import re
import unicodedata

_VERBE_OUTRE = (
    r"(?:ignore[rz]?|oublie[rz]?|neglige[rz]?|contourne[rz]?|ne tiens? pas compte|"
    r"ne tenez pas compte|disregard|forget|override|bypass)"
)
_CIBLE = (
    r"(?:consignes?|instructions?|regles?|directives?|baremes?|garde-?fous?|guidelines?|rules?|"
    r"prompts?|restrictions?)"
)
# s'adresse à l'assistant : possessif de 2e personne, « toutes », « précédentes »
_DE_L_ASSISTANT = r"(?:tes|vos|ton|votre|your|toutes? (?:les )?|all (?:the )?|previous|prior|above)"
_DECIDER = (
    r"(?:\b(?:accepte[rz]?|valide[rz]?|approuve[rz]?|approve)\s+(?:ce|cet|le|this|the|every|all|"
    r"tous les)\s+(?:dossiers?|contrats?|files?|applications?|contracts?)\b"
    r"|\bdecision\s+(?:accepte|approved)\b|\bstatut\s+(?:a|en)\s+accepte\b)"
)
_MARQUEUR = (
    r"(?:quoi qu'il arrive|quel(?:le)? que soit|meme si|sans (?:aucune )?verif\w*|sans condition|"
    r"obligatoire|whatever|regardless|no matter|c'est un ordre)"
)

# nom : (description en une ligne, motif sur texte normalisé)
MOTIFS: dict[str, tuple[str, re.Pattern[str]]] = {
    nom: (doc, re.compile(motif, re.S))
    for nom, (doc, motif) in {
        "passer_outre": (
            "ordre d'ignorer/oublier les consignes, règles ou instructions DE l'assistant",
            rf"\b{_VERBE_OUTRE}\b.{{0,25}}\b{_DE_L_ASSISTANT}\b.{{0,25}}\b{_CIBLE}\b",
        ),
        "changement_de_role": (
            "changement de rôle de l'assistant : « tu es maintenant », « you are now », « act as »",
            r"\b(?:tu es maintenant|tu n'es plus|a partir de maintenant,? tu|agis comme|"
            r"fais comme si tu|you are now|act as|pretend (?:to be|you)|desormais,? "
            r"(?:reponds|tu dois))\b",
        ),
        "prompt_systeme": (
            "demande du prompt système ou des instructions de l'assistant (révèle, affiche…)",
            r"\b(?:prompt systeme|system prompt)\b|\b(?:revele[rz]?|affiche[rz]?|montre[rz]?|"
            r"repete[rz]?|print|reveal|show|display|repeat)\b.{0,30}\b(?:tes|vos|your)\s+"
            r"(?:instructions|consignes|prompt)|\b(?:instructions|consignes)\b.{0,20}\b"
            r"(?:que tu as recues|de depart)\b",
        ),
        "ordre_de_decider": (
            "ordre d'accepter/valider le dossier AVEC un marqueur d'injection (quoi qu'il arrive…)",
            rf"(?=.*{_DECIDER})(?=.*{_MARQUEUR})",
        ),
        "ordre_de_statut": (
            "ordre de fixer prime, statut ou score à une valeur favorable (accepte, minimum, zéro)",
            r"\b(?:mets|met|passe|fixe|set)\b.{0,25}\b(?:prime|statut|score|decision|status|"
            r"premium)\b.{0,15}\b(?:a|au|en|to|at)\s+(?:accepte|minimum|zero|0|1 euro|approved)\b",
        ),
        "balise_evasion": (
            "balises techniques d'évasion : </donnees_non_fiables>, ### system, [INST], [SYSTÈME]",
            r"</?donnees_non_fiables>|###\s*system|\[/?inst\]|\[/?systeme?\]",
        ),
        "donnees_identite": (
            "demande à l'assistant l'identité du souscripteur ou les données d'autres dossiers",
            r"\b(?:donne|communique|fournis|dis|give|tell)(?:-moi| me)\b.{0,30}\b"
            r"(?:nom|adresse|numero|iban|telephone|mail|email|naissance|permis)\b.{0,30}\b"
            r"(?:souscripteur|assure|client|conducteur|titulaire|policyholder|customer)|"
            r"\b(?:donne|communique|fournis|liste|give|tell)(?:-moi| me)\b.{0,30}\b"
            r"(?:dossiers?|contrats?|clients?)\b.{0,20}\b(?:autres?|portefeuille|other)\b|"
            r"\b(?:donne|communique|fournis|liste|give|tell)(?:-moi| me)\b.{0,30}\b"
            r"(?:autres?|other)\s+(?:dossiers?|contrats?|clients?)",
        ),
        "secrets": (
            "demande à l'assistant ses clés, jetons, mots de passe ou variables d'environnement",
            r"\b(?:tes|vos|your)\b.{0,30}\b(?:cles? d'api|api keys?|jetons?|tokens?|"
            r"mots? de passe|variables? d'environnement)\b|\b(?:cles? d'api|api keys?|jetons?|"
            r"variables? d'environnement)\b.{0,30}\bque tu\b",
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
