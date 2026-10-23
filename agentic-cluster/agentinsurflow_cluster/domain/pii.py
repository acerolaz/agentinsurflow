"""Détection de données personnelles (e-mail, téléphone FR, IBAN FR), en entrée et en sortie."""

import re

_MOTIFS = {
    "email": re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    "telephone": re.compile(r"(?<![\w+])(?:\+33\s?|0)[1-9](?:[ .-]?\d{2}){4}(?!\d)"),
    "iban": re.compile(r"\bFR\d{2}(?:\s?[0-9A-Z]{4}){5}\s?[0-9A-Z]{3}\b", re.IGNORECASE),
}


def pii_detectees(texte: str) -> list[str]:
    """Types de données personnelles trouvés dans `texte` ⊂ {email, telephone, iban}."""
    return [type_ for type_, motif in _MOTIFS.items() if motif.search(texte)]
