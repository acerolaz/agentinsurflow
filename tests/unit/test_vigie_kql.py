"""Vigie S2 : requêtes KQL versionnées et catalogue des alertes AL-1 → AL-9."""

import re
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
VIGIE = RACINE / "infra" / "vigie"
KQL = VIGIE / "kql"

LIGNES = {  # id: (kql, frequence, fenetre, operateur, seuil, gravite) — spec §4 et §5
    "AL-1": ("al-1-latence-p95.kql", "15m", "15m", ">", "30000", "2"),
    "AL-2": ("al-2-llm-ko.kql", "5m", "5m", ">=", "1", "1"),
    "AL-3": ("al-3-garde-fous-chargement.kql", "5m", "5m", ">", "180", "1"),
    "AL-4": ("al-4-mcp-indisponible.kql", "5m", "5m", ">=", "1", "1"),
    "AL-5": ("al-5-revue-humaine.kql", "1h", "2h", ">", "30", "2"),
    "AL-6": ("al-6-cout-dossier.kql", "1h", "24h", ">", "0.15", "2"),
    "AL-7": ("al-7-refus-garde-fous.kql", "1h", "48h", ">", "2", "2"),
    "AL-8": ("al-8-foundry-429.kql", "1h", "1h", ">=", "env:SEUIL_AL8", "2"),
    "AL-9": ("al-9-gateway-403.kql", "1h", "1h", ">=", "env:SEUIL_AL9", "2"),
}
ALERTES = sorted(KQL.glob("al-*.kql"))
TUILES = sorted((KQL / "tuiles").glob("*.kql"))


def lire(nom):
    return (KQL / nom).read_text()


def test_catalogue_fidele_a_la_spec():
    lignes = (VIGIE / "alertes.tsv").read_text().splitlines()
    assert lignes[0].split("\t") == "id kql frequence fenetre operateur seuil gravite ancre".split()
    obtenu = {}
    for ligne in lignes[1:]:
        id_, *reste, ancre = ligne.split("\t")
        assert ancre == id_.lower()
        obtenu[id_] = tuple(reste)
    assert obtenu == LIGNES


def test_chaque_requete_existe_et_produit_valeur():
    for id_, (nom, *_) in LIGNES.items():
        assert re.search(r"\bvaleur\b", lire(nom)), id_


def test_les_tuiles_existent():
    assert {t.name for t in TUILES} == {
        "evaluations-par-heure.kql",
        "revue-par-cause.kql",
        "cout-par-agent.kql",
        "sans-decision.kql",
        "disponibilite.kql",
        "frequence-glm.kql",  # #155 : pas encore dans dashboard.json
    }


def test_filtre_par_ressource():
    for f in ALERTES + TUILES:
        if f.name.startswith("al-3"):
            assert "$CLUSTER_APP" in f.read_text()
        else:
            assert "$APPI_ID" in f.read_text(), f.name


def test_volume_minimal_al5_al7():
    for nom in ("al-5-revue-humaine.kql", "al-7-refus-garde-fous.kql"):
        texte = lire(nom)
        assert re.search(r"iff\(n\w* < 10", texte) and "real(null)" in texte


def test_cout_sans_prix_en_dur():
    for nom in ("al-6-cout-dossier.kql", "tuiles/cout-par-agent.kql"):
        texte = lire(nom)
        assert "datatable(modele:string, entree:real, sortie:real)[$PRIX_KQL]" in texte
        code = "\n".join(ligne.split("//")[0] for ligne in texte.splitlines())
        assert not re.search(r"\d+\.\d+", code), nom


def test_aucun_dollar_parasite():
    for f in ALERTES + TUILES:
        restes = re.sub(r"\$(APPI_ID|CLUSTER_APP|PRIX_KQL)\b", "", f.read_text())
        assert "$" not in restes, f.name
