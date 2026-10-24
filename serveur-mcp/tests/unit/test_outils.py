"""Unitaires — cas d'usage des outils de lecture, ports simulés seulement."""

from __future__ import annotations

import datetime

import pytest
from fakes_mcp import FauxCorpus, FauxDossiers, FauxJetons, appelant

from agentinsurflow_mcp.application.outils import (
    enregistrer_brouillon,
    enregistrer_etat,
    get_contrat,
    lister_pieces,
    search_rag,
    update_statut_dossier,
)
from agentinsurflow_mcp.domain.models import (
    ARGUMENTS_INVALIDES,
    CONTRAT_INTROUVABLE,
    DOSSIERS_INDISPONIBLES,
    NOT_FOUND_IN_CORPUS,
    ErreurOutil,
    Fiche,
    PrimeBrouillon,
)


async def test_search_rag_passe_le_jeton_obo_rag() -> None:
    jetons, corpus = FauxJetons(), FauxCorpus()
    resultat = await search_rag(appelant(), jetons, corpus, "franchise ?", 3)
    assert jetons.demandes == [("jeton-entrant", "rag")]
    assert corpus.appels == [("obo-rag", "franchise ?", 3)]
    assert resultat["statut"] == "OK"


async def test_search_rag_propage_not_found_in_corpus() -> None:
    corpus = FauxCorpus(ErreurOutil(NOT_FOUND_IN_CORPUS, "hors corpus"))
    with pytest.raises(ErreurOutil) as exc:
        await search_rag(appelant(), FauxJetons(), corpus, "recette de crêpes")
    assert exc.value.code == NOT_FOUND_IN_CORPUS


async def test_get_contrat_passe_le_jeton_obo_underwriting() -> None:
    jetons, dossiers = FauxJetons(), FauxDossiers()
    resultat = await get_contrat(appelant("saga"), jetons, dossiers, "AIF/1")
    assert jetons.demandes == [("jeton-entrant", "underwriting")]
    assert dossiers.appels == [("obo-underwriting", "AIF/1")]
    assert resultat == {"numero_contrat": "AIF/1"}


async def test_get_contrat_introuvable() -> None:
    dossiers = FauxDossiers(ErreurOutil(CONTRAT_INTROUVABLE, "introuvable"))
    with pytest.raises(ErreurOutil) as exc:
        await get_contrat(appelant("saga"), FauxJetons(), dossiers, "X")
    assert exc.value.code == CONTRAT_INTROUVABLE


async def test_obo_refuse_dossiers_indisponibles_sans_appel_backend() -> None:
    dossiers = FauxDossiers()
    with pytest.raises(ErreurOutil) as exc:
        await get_contrat(appelant("saga"), FauxJetons(refuse=True), dossiers, "X")
    assert exc.value.code == DOSSIERS_INDISPONIBLES
    assert dossiers.appels == []


FICHE = Fiche("ACCEPTE", "tous_risques", 12.5, "2026.1", ["R1"], ["bon profil"], ["art. 3"])


async def test_enregistrer_brouillon_corps_snake_case_avec_prime() -> None:
    jetons, dossiers = FauxJetons(), FauxDossiers()
    prime = PrimeBrouillon(480.0, "mensuelle", datetime.date(2026, 11, 1))
    resultat = await enregistrer_brouillon(
        appelant("saga"), jetons, dossiers, "AIF/1", FICHE, prime
    )
    assert resultat == {"ecrit": True}
    assert jetons.demandes == [("jeton-entrant", "underwriting")]
    assert dossiers.ecritures == [
        (
            "brouillon",
            "obo-underwriting",
            "AIF/1",
            {
                "fiche": {
                    "decision": "ACCEPTE",
                    "contrat_type": "tous_risques",
                    "score": 12.5,
                    "version_bareme": "2026.1",
                    "regle_ids": ["R1"],
                    "motifs": ["bon profil"],
                    "citations": ["art. 3"],
                },
                "prime": {
                    "prime_ttc": 480.0,
                    "periodicite": "mensuelle",
                    "date_effet": "2026-11-01",
                },
            },
        )
    ]


async def test_enregistrer_brouillon_sans_prime_envoie_null() -> None:
    dossiers = FauxDossiers()
    await enregistrer_brouillon(appelant("saga"), FauxJetons(), dossiers, "A", FICHE)
    assert dossiers.ecritures[0][3]["prime"] is None


async def test_update_statut_sans_validation() -> None:
    dossiers = FauxDossiers()
    resultat = await update_statut_dossier(
        appelant("saga"), FauxJetons(), dossiers, "AIF/1", "REVUE_HUMAINE"
    )
    assert resultat == {"ecrit": True}
    assert dossiers.ecritures == [
        ("statut", "obo-underwriting", "AIF/1", {"statut": "REVUE_HUMAINE", "validation": None})
    ]


async def test_update_statut_avec_validation() -> None:
    dossiers = FauxDossiers()
    await update_statut_dossier(appelant("saga"), FauxJetons(), dossiers, "A", "ACCEPTE", "VALIDEE")
    assert dossiers.ecritures[0][3] == {"statut": "ACCEPTE", "validation": "VALIDEE"}


async def test_ecriture_refusee_par_le_backend_propage_le_code() -> None:
    dossiers = FauxDossiers(ErreurOutil(ARGUMENTS_INVALIDES, "VALIDATION_EXIGEE"))
    with pytest.raises(ErreurOutil) as exc:
        await update_statut_dossier(appelant("saga"), FauxJetons(), dossiers, "A", "ACCEPTE")
    assert exc.value.code == ARGUMENTS_INVALIDES


async def test_lister_pieces_renvoie_les_metadonnees_du_depot() -> None:
    dossiers = FauxDossiers()
    resultat = await lister_pieces(appelant("pieces"), FauxJetons(), dossiers, "AIF/1")
    assert resultat == {"pieces": [{"type": "releve_information", "date_emission": "2026-09-01"}]}
    assert dossiers.appels == [("obo-underwriting", "AIF/1")]


async def test_lister_pieces_contrat_hors_portefeuille() -> None:
    dossiers = FauxDossiers(ErreurOutil(CONTRAT_INTROUVABLE, "introuvable"))
    with pytest.raises(ErreurOutil) as exc:
        await lister_pieces(appelant("pieces"), FauxJetons(), dossiers, "A")
    assert exc.value.code == CONTRAT_INTROUVABLE


async def test_enregistrer_etat_transmet_le_corps_tel_quel() -> None:
    etat = {
        "statut_parcours": "EN_COURS",
        "tentative": 1,
        "sections": [{"section": "pieces", "contenu": {"ok": True}}],
        "rapports": [],
        "tours": [],
    }
    dossiers = FauxDossiers()
    resultat = await enregistrer_etat(appelant("saga"), FauxJetons(), dossiers, "A", etat)
    assert resultat == {"ecrit": True}
    assert dossiers.ecritures == [("etat", "obo-underwriting", "A", etat)]


async def test_enregistrer_etat_refuse_par_le_backend_propage_le_code() -> None:
    dossiers = FauxDossiers(ErreurOutil(ARGUMENTS_INVALIDES, "SECTION_INCONNUE"))
    with pytest.raises(ErreurOutil) as exc:
        await enregistrer_etat(appelant("saga"), FauxJetons(), dossiers, "A", {})
    assert exc.value.code == ARGUMENTS_INVALIDES
