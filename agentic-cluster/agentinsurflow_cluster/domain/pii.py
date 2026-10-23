"""Détection de données personnelles (e-mail, téléphone FR, IBAN FR), en entrée et en sortie."""

import re

_ESP = " \u00a0\u202f"  # espace, insécable, insécable fine
_SEP = rf"[{_ESP}.\-]"
_MOTIFS = {
    "email": re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    # Préfixe +33 / 0033 / 0, puis soit 8 chiffres compacts, soit 4 groupes de 2 séparés par
    # le même séparateur ; isolé (ni mot, ni chiffre, ni suite « ,50 » / « 06 » collée).
    "telephone": re.compile(
        rf"(?<![\w+])(?<!\d{_SEP})(?:\+33[{_ESP}]?(?:\(0\)[{_ESP}]?)?|0033[{_ESP}]?(?:\(0\)[{_ESP}]?)?|0)"
        rf"[1-9](?:\d{{8}}|({_SEP})\d{{2}}(?:\1\d{{2}}){{3}})(?!\d|{_SEP}\d|,\d)"
    ),
    "iban": re.compile(
        rf"\bFR\d{{2}}(?:[{_ESP}\-]?[0-9A-Z]{{4}}){{5}}[{_ESP}\-]?[0-9A-Z]{{3}}\b", re.IGNORECASE
    ),
}


def pii_detectees(texte: str) -> list[str]:
    """Types de données personnelles trouvés dans `texte` ⊂ {email, telephone, iban}."""
    return [type_ for type_, motif in _MOTIFS.items() if motif.search(texte)]
