"""TU — garde-fous purs : un cas par règle."""

from agentinsurflow_cluster.domain.garde_fous import ga, gf, gp, gr
from agentinsurflow_cluster.domain.models import Fiche, Pieces, Prime, Risque

EXIGEES = ("permis", "releve_information")
CONNUES = ("permis", "releve_information", "carte_grise")
REF_P = Pieces("incomplet", ("permis",), "")
REF_R = Risque(2, "refus", ("R01_SUSPENSION",), "bareme-2026.10-v1", "")
SOURCES = (
    {"doc_id": "legi-1", "collection": "legifrance", "regle_id": "R01_SUSPENSION"},
    {"doc_id": "tiers", "collection": "notices_produits", "regle_id": None},
    {"doc_id": "jeunes_conducteurs", "collection": "notices_produits", "regle_id": None},
)


def _pieces(**kw: object) -> Pieces:
    base = {"statut": "incomplet", "manquantes": ("permis",), "note": "Pièce manquante : permis."}
    return Pieces(**{**base, **kw})  # type: ignore[arg-type]


def _risque(**kw: object) -> Risque:
    note = "Règle R01_SUSPENSION, barème bareme-2026.10-v1, score 2."
    base = {
        "score": 2,
        "classe": "refus",
        "regle_ids": ("R01_SUSPENSION",),
        "version_bareme": "bareme-2026.10-v1",
        "note": note,
    }
    return Risque(**{**base, **kw})  # type: ignore[arg-type]


def _fiche(**kw: object) -> Fiche:
    base = {
        "decision": "REFUSE",
        "contrat_type": "tiers",
        "score": 2.0,
        "version_bareme": "bareme-2026.10-v1",
        "regle_ids": ("R01_SUSPENSION",),
        "motifs": ("suspension de permis",),
        "citations": ("legi-1",),
    }
    return Fiche(**{**base, **kw})  # type: ignore[arg-type]


def _gp(p: Pieces) -> list[str]:
    return gp(p, REF_P, EXIGEES, CONNUES)


def test_gp_valide() -> None:
    assert _gp(_pieces()) == []


def test_gp1() -> None:
    assert "GP1" in _gp(_pieces(statut="complet"))
    assert "GP1" in _gp(_pieces(manquantes=("releve_information",), note="releve_information"))


def test_gp2() -> None:
    assert "GP2" in _gp(_pieces(note="Dossier à compléter."))


def test_gp3() -> None:
    assert "GP3" in _gp(_pieces(note="Pièce manquante : permis. Appeler le 06 12 34 56 78"))


def test_gp4() -> None:
    assert "GP4" in _gp(_pieces(note="Pièce manquante : permis ; fournir aussi la carte_grise."))


def test_gr_valide() -> None:
    assert gr(_risque(), REF_R) == []


def test_gr1() -> None:
    assert "GR1" in gr(_risque(score=3, note=_risque().note.replace("2", "3")), REF_R)


def test_gr2() -> None:
    assert "GR2" in gr(_risque(note="Score 2, refus."), REF_R)


def test_gr3() -> None:
    assert "GR3" in gr(_risque(note=_risque().note + " 87 % de sinistres."), REF_R)
    assert "GR3" in gr(_risque(note=_risque().note + " Appeler jean@x.fr"), REF_R)


def test_gf_valide() -> None:
    assert gf(_fiche(), REF_R, SOURCES, "tiers") == []


def test_gf1() -> None:
    assert "GF1" in gf(_fiche(motifs=()), REF_R, SOURCES, "tiers")


def test_gf2() -> None:
    risque = Risque(2, "acceptable", ("R01_SUSPENSION",), "bareme-2026.10-v1", "")
    assert gf(_fiche(decision="REFUSE"), risque, SOURCES, "tiers") == ["GF2"]


def test_gf3() -> None:
    assert "GF3" in gf(_fiche(version_bareme="autre"), REF_R, SOURCES, "tiers")


def test_gf4() -> None:
    assert "GF4" in gf(_fiche(citations=("inconnu",)), REF_R, SOURCES, "tiers")
    assert "GF4" in gf(_fiche(citations=()), REF_R, SOURCES, "tiers")


def test_gf5() -> None:
    assert "GF5" in gf(_fiche(citations=("tiers",)), REF_R, SOURCES, "tiers")


def test_gf6() -> None:
    risque = Risque(0, "acceptable", (), "bareme-2026.10-v1", "")
    ok = _fiche(decision="ACCEPTE", score=0.0, regle_ids=(), citations=("tiers",))
    assert gf(ok, risque, SOURCES, "tiers") == []
    ko = _fiche(
        decision="ACCEPTE", score=0.0, regle_ids=(), contrat_type="legi-1", citations=("legi-1",)
    )
    assert gf(ko, risque, SOURCES, "tiers") == ["GF6"]


def test_gf6_contrat_type_doit_etre_la_notice_de_la_formule() -> None:
    # P13 : une notice présente mais d'une autre formule (ou complémentaire) ne vaut pas
    risque = Risque(0, "acceptable", (), "bareme-2026.10-v1", "")
    for contrat_type in ("jeunes_conducteurs", "tiers"):
        fiche = _fiche(
            decision="ACCEPTE", score=0.0, regle_ids=(), contrat_type=contrat_type,
            citations=(contrat_type,),
        )  # fmt: skip
        assert gf(fiche, risque, SOURCES, "tous_risques") == ["GF6"]


def test_gf7() -> None:
    assert "GF7" in gf(
        _fiche(motifs=("IBAN FR76 3000 6000 0112 3456 7890 189",)), REF_R, SOURCES, "tiers"
    )


REF_A = Prime("600.00", "50.00", "tarif-v1", "")


def _prime(**kw: object) -> Prime:
    base = {
        "prime_ttc_annuelle": "600.00",
        "prime_mensuelle": "50.00",
        "version_formule": "tarif-v1",
        "explication": "Barème tarif-v1.",
    }
    return Prime(**{**base, **kw})  # type: ignore[arg-type]


def test_ga_valide() -> None:
    assert ga(_prime(), REF_A) == []


def test_ga1() -> None:
    assert ga(_prime(prime_ttc_annuelle="700.00"), REF_A) == ["GA1"]


def test_ga2() -> None:
    assert ga(_prime(explication="Sans version."), REF_A) == ["GA2"]


def test_ga3() -> None:
    assert ga(_prime(explication="tarif-v1, jean@x.fr"), REF_A) == ["GA3"]
