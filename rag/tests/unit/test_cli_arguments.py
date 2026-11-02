"""Unitaires — arguments de la CLI d'ingestion refusés avant toute I/O."""

from __future__ import annotations

import pytest

from agentinsurflow_rag.cli import ingest


@pytest.mark.parametrize(
    "arguments",
    [["--source", "x"], ["--collection", "notices_produits"]],
)
def test_collection_et_source_vont_ensemble(
    arguments: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert ingest.main(arguments) == 1
    assert "--source" in capsys.readouterr().err


def test_option_date_malformee_message_clair(capsys: pytest.CaptureFixture[str]) -> None:
    assert ingest.main(["--date", "20/10/2026", "--sans-envoi"]) == 1
    assert "Invalid isoformat string" in capsys.readouterr().err
