"""TU — détection des données personnelles (e-mail, téléphone, IBAN)."""

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
