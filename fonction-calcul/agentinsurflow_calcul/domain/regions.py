"""Département -> ancienne région INSEE d'avant 2016, avec les codes de freMTPL2 (stdlib seule).

Source : code officiel géographique de l'INSEE (anciennes régions métropolitaines, 22 régions).
Les DOM (971-976) n'ont pas de région freMTPL2 : absents de la table, donc hors modèle.
"""

_DEPARTEMENTS_PAR_REGION: dict[str, tuple[str, ...]] = {
    "R11": ("75", "77", "78", "91", "92", "93", "94", "95"),  # Île-de-France
    "R21": ("08", "10", "51", "52"),  # Champagne-Ardenne
    "R22": ("02", "60", "80"),  # Picardie
    "R23": ("27", "76"),  # Haute-Normandie
    "R24": ("18", "28", "36", "37", "41", "45"),  # Centre
    "R25": ("14", "50", "61"),  # Basse-Normandie
    "R26": ("21", "58", "71", "89"),  # Bourgogne
    "R31": ("59", "62"),  # Nord-Pas-de-Calais
    "R41": ("54", "55", "57", "88"),  # Lorraine
    "R42": ("67", "68"),  # Alsace
    "R43": ("25", "39", "70", "90"),  # Franche-Comté
    "R52": ("44", "49", "53", "72", "85"),  # Pays de la Loire
    "R53": ("22", "29", "35", "56"),  # Bretagne
    "R54": ("16", "17", "79", "86"),  # Poitou-Charentes
    "R72": ("24", "33", "40", "47", "64"),  # Aquitaine
    "R73": ("09", "12", "31", "32", "46", "65", "81", "82"),  # Midi-Pyrénées
    "R74": ("19", "23", "87"),  # Limousin
    "R82": ("01", "07", "26", "38", "42", "69", "73", "74"),  # Rhône-Alpes
    "R83": ("03", "15", "43", "63"),  # Auvergne
    "R91": ("11", "30", "34", "48", "66"),  # Languedoc-Roussillon
    "R93": ("04", "05", "06", "13", "83", "84"),  # Provence-Alpes-Côte d'Azur
    "R94": ("2A", "2B"),  # Corse
}

REGION_PAR_DEPARTEMENT: dict[str, str] = {
    dep: region for region, deps in _DEPARTEMENTS_PAR_REGION.items() for dep in deps
}
