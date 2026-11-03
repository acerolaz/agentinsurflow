"""TU — ``tools/benchmark_synthese.py`` : des mesures du benchmark aux verdicts de C7."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.benchmark_synthese import (
    charger_rag,
    cout_usd,
    parser_prix,
    prix_retenu,
    synthese_agents,
    tableaux_markdown,
    verdict,
)

AGENTS = ("pieces", "analyste", "redacteur", "actuaire")


def _mesure(
    agent: str, statut: str = "ok", entree: int = 1000, sortie: int = 100
) -> dict[str, object]:
    return {
        "modele": "m",
        "agent": agent,
        "dossier": "A",
        "essai": 1,
        "latence_s": 1.0,
        "statut": statut,
        "cause": None if statut == "ok" else "llm_ko",
        "tokens_entree": entree,
        "tokens_sortie": sortie,
        "nb_sources": 0,
    }


def test_parser_prix_normalise_1k_et_1m() -> None:
    items = [
        {"meterName": "gpt 4.1 mini Inp glbl Tokens", "retailPrice": 0.0004, "unitOfMeasure": "1K"},
        {
            "meterName": "GPT 5 Mini outpt DZone 1M Tokens",
            "retailPrice": 2.2,
            "unitOfMeasure": "1M",
        },
        {"meterName": "FW Kimi K2.5 Inp DZ Tokens", "retailPrice": 0.00066, "unitOfMeasure": "1K"},
    ]
    p = parser_prix(items)
    assert p["gpt-4.1-mini"]["global"]["entree"] == pytest.approx(0.40)
    assert p["gpt-5-mini"]["data_zone"]["sortie"] == pytest.approx(2.20)
    assert p["Kimi-K2.5"]["data_zone"]["entree"] == pytest.approx(0.66)


def test_parser_prix_ignore_cache_et_regional() -> None:
    items = [
        {
            "meterName": "GPT 5 Mini cchd Inpt Glbl 1M Tokens",
            "retailPrice": 0.025,
            "unitOfMeasure": "1M",
        },
        {
            "meterName": "gpt 4.1 mini Inp regnl Tokens",
            "retailPrice": 0.000484,
            "unitOfMeasure": "1K",
        },
    ]
    assert parser_prix(items) == {}


def test_prix_global_absent_retient_data_zone() -> None:
    prix = {"Kimi-K2.5": {"data_zone": {"entree": 0.66, "sortie": 3.30}}}
    assert prix_retenu(prix, "Kimi-K2.5") == ({"entree": 0.66, "sortie": 3.30}, "data_zone")


def test_prix_global_prefere_si_present() -> None:
    prix = {
        "m": {"global": {"entree": 1.0, "sortie": 2.0}, "data_zone": {"entree": 3.0, "sortie": 4.0}}
    }
    assert prix_retenu(prix, "m") == ({"entree": 1.0, "sortie": 2.0}, "global")


def test_cout() -> None:
    assert cout_usd(1_000_000, 1_000_000, {"entree": 0.40, "sortie": 1.60}) == pytest.approx(2.00)


@pytest.mark.parametrize(
    ("taux", "attendu"), [(0.8, "répond"), (0.79, "ne répond pas"), (None, "ne répond pas")]
)
def test_verdict_seuil(taux: float | None, attendu: str) -> None:
    assert verdict(taux, True, True, True) == attendu


def test_verdict_sortie_non_structuree_bloque() -> None:
    assert verdict(1.0, False, True, True) == "ne répond pas"


def test_verdict_outil_ko_bloque() -> None:
    assert verdict(1.0, True, False, True) == "ne répond pas"


def test_verdict_non_deployable_bloque() -> None:
    assert verdict(1.0, True, True, False) == "ne répond pas"


def test_rag_refuse_si_le_modele_observe_differe(tmp_path: Path) -> None:
    f = tmp_path / "r.json"
    f.write_text(
        json.dumps(
            {
                "manifeste": {"modele": {"observe": ["Kimi-K2.5"]}},
                "taux": 1.0,
                "latence_p95_s": 1,
                "resultats": [],
            }
        )
    )
    with pytest.raises(ValueError):
        charger_rag(f, "gpt-5-mini")


def test_rag_lit_le_rapport(tmp_path: Path) -> None:
    f = tmp_path / "r.json"
    f.write_text(
        json.dumps(
            {
                "manifeste": {"modele": {"observe": ["m"]}},
                "taux": 0.9,
                "latence_p95_s": 2.5,
                "resultats": [{}, {}],
            }
        )
    )
    assert charger_rag(f, "m") == {"modele": "m", "taux": 0.9, "latence_p95_s": 2.5, "resultats": 2}


def test_modele_sans_reussite_sans_chiffres() -> None:
    mesures = [_mesure(a, "echec", 0, 0) for a in AGENTS]
    s = synthese_agents(mesures, {"m": {"global": {"entree": 1.0, "sortie": 1.0}}})
    assert s["m"]["agents"]["pieces"]["ok"] == 0
    assert s["m"]["agents"]["pieces"]["p95_s"] is None
    assert s["m"]["cout_dossier_usd"] is None
    assert "—" in tableaux_markdown([], s)


def test_cout_dossier_somme_les_quatre_agents() -> None:
    mesures = [_mesure(a) for a in AGENTS]
    s = synthese_agents(mesures, {"m": {"global": {"entree": 1.0, "sortie": 10.0}}})
    # Chaque agent : 1000 × 1 $/M + 100 × 10 $/M = 0,002 $ ; quatre agents : 0,008 $.
    assert s["m"]["cout_dossier_usd"] == pytest.approx(0.008)
    assert s["m"]["reference_prix"] == "global"


def test_tableau_signale_le_prix_de_reference_data_zone() -> None:
    mesures = [_mesure(a) for a in AGENTS]
    s = synthese_agents(mesures, {"m": {"data_zone": {"entree": 1.0, "sortie": 1.0}}})
    assert "réf. Data Zone" in tableaux_markdown([], s)


def test_causes_d_echec_comptees() -> None:
    mesures = [_mesure("pieces", "echec"), _mesure("pieces", "echec"), _mesure("pieces")]
    s = synthese_agents(mesures, {"m": {"global": {"entree": 1.0, "sortie": 1.0}}})
    assert s["m"]["agents"]["pieces"]["causes"] == {"llm_ko": 2}
    assert s["m"]["agents"]["pieces"]["essais"] == 3
