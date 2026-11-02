"""Unitaires — validation des DTO d'entrée, variation par variation.

Le refus HTTP (422) reste prouvé par un cas dans ``rag/tests/integration`` : ici, seule la règle.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from agentinsurflow_rag.api.schemas.agent import Question
from agentinsurflow_rag.api.schemas.corpus import LotIngestion
from corpus_de_test import CORPUS, DATE_ISO, SHA


def lot(articles: list[dict[str, Any]] | None = None, **autres: Any) -> dict[str, Any]:
    return {
        "collection": "textes_reglementaires",
        "instantane_sha256": SHA,
        "instantane_date": DATE_ISO,
        "articles": CORPUS if articles is None else articles,
    } | autres


def test_lot_valide_accepte() -> None:
    assert LotIngestion.model_validate(lot()).collection == "textes_reglementaires"


@pytest.mark.parametrize(
    "corps",
    [
        lot(collection="cgv_conditions"),  # dans le CHECK de la base, pas ingérable
        lot([CORPUS[0] | {"regle_id": "r01"}]),
        lot([CORPUS[0] | {"regle_id": "R1_X"}]),
        lot(instantane_sha256="pas-un-sha"),
        lot([]),
        lot(CORPUS * 13),  # 52 articles > 50
    ],
)
def test_lot_invalide_refuse(corps: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        LotIngestion.model_validate(corps)


def test_lot_sans_date_d_instantane_refuse() -> None:
    corps = lot()
    del corps["instantane_date"]
    with pytest.raises(ValidationError):
        LotIngestion.model_validate(corps)


@pytest.mark.parametrize("numero", ["AIF 2026", "x" * 41])
def test_numero_contrat_invalide_refuse(numero: str) -> None:
    with pytest.raises(ValidationError):
        Question.model_validate({"texte": "Une question", "numero_contrat": numero})


def test_numero_contrat_bien_forme_accepte() -> None:
    q = Question.model_validate({"texte": "Une question", "numero_contrat": "AIF-2026-000001"})
    assert q.numero_contrat == "AIF-2026-000001"
