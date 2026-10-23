"""TU — détection des données personnelles (e-mail, téléphone, IBAN)."""

import pytest

from agentinsurflow_cluster.domain.pii import pii_detectees


def test_telephone() -> None:
    assert pii_detectees("appelez le 06 12 34 56 78") == ["telephone"]
    assert pii_detectees("au +33 6 12 34 56 78") == ["telephone"]


def test_iban() -> None:
    assert pii_detectees("FR76 3000 6000 0112 3456 7890 189") == ["iban"]


def test_email() -> None:
    assert pii_detectees("écrire à jean.dupont@exemple.fr") == ["email"]


def test_rien() -> None:
    assert pii_detectees("client fidèle depuis 2019") == []


@pytest.mark.parametrize(
    "texte",
    [
        "+33 (0)6 12 34 56 78",
        "0033 6 12 34 56 78",
        "06 12 34 56 78",
        "06.12.34.56.78",
        "0612345678",
        "06\u00a012\u00a034\u00a056\u00a078",
        "06\u202f12\u202f34\u202f56\u202f78",
    ],
)
def test_telephones_positifs(texte: str) -> None:
    assert pii_detectees(texte) == ["telephone"]


@pytest.mark.parametrize(
    "texte",
    [
        "bareme-2026.10-v1",
        "1234,56 EUR",
        "AIF-2026-000004",
        "1 234 567 890",
        "IBAN DE89 3704 0044 0532 0130 00",
        "montant 0612345678,50",
        "le 01 02 03 04 05 06",
    ],
)
def test_aucun_telephone(texte: str) -> None:
    assert "telephone" not in pii_detectees(texte)


@pytest.mark.parametrize(
    "texte", ["FR7630006000011234567890189", "FR76-3000-6000-0112-3456-7890-189"]
)
def test_iban_sans_espaces_ou_avec_tirets(texte: str) -> None:
    assert pii_detectees(texte) == ["iban"]
