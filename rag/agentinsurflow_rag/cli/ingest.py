"""CLI d'ingestion (spec §3.2, ① à ④) : Légifrance → instantané versionné → ``/api/ingestions``.

    make ingest [URL=https://<gateway>] [INSTANTANE=data/raw/code-assurances-<date>.json]

① jeton PISTE (``.env`` local) ; ② plan du code, filtre du périmètre, ``getArticle`` séquentiel ;
③ instantané écrit dans un fichier temporaire puis renommé (jamais partiel), avec son manifeste ;
④ lots de 50 vers l'API, par la gateway, avec un jeton Entra (rôle ``Ingestion``).
``--instantane`` rejoue un fichier et saute ① à ③ (CI, staging, production : pas de PISTE).
Les traces de la CLI partent aussi par la gateway (``/v1/traces``, rôle ``Telemetrie``) ;
leur échec ne fait jamais échouer l'ingestion.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import subprocess
import sys
from collections.abc import Sequence
from datetime import date as Date
from pathlib import Path
from typing import Any

import httpx
from opentelemetry import propagate
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Tracer
from pydantic import ValidationError

from ..infrastructure.legifrance.client import (
    PERIMETRE,
    ConfigLegifrance,
    ErreurPiste,
    extraire,
    jeton_piste,
)

TAILLE_LOT = 50
DELAI_API_S = 120

journal = logging.getLogger("agentinsurflow.ingest")


class ErreurEnvoi(Exception):
    """L'API a refusé un lot (jeton, rôle, validation) ou n'a pas répondu."""


def nouveau_client() -> httpx.Client:
    return httpx.Client(timeout=DELAI_API_S)


# ---------------------------------------------------------------- instantané


def sha_articles(articles: Sequence[Any]) -> str:
    """SHA-256 du JSON canonique des articles (clés triées, sans espaces)."""
    canonique = json.dumps(articles, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonique.encode("utf-8")).hexdigest()


def sauvegarder_instantane(
    articles: list[dict[str, Any]], dossier: Path, environnement: str, date: str
) -> Path:
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / f"code-assurances-{date}.json"
    contenu = {
        "manifeste": {
            "date": date,
            "environnement": environnement,
            "perimetre": PERIMETRE.pattern,
            "articles": len(articles),
            "sha256": sha_articles(articles),
        },
        "articles": articles,
    }
    temporaire = chemin.with_suffix(".json.tmp")
    temporaire.write_text(json.dumps(contenu, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(temporaire, chemin)  # atomique : jamais d'instantané partiel
    return chemin


def lire_instantane(chemin: Path) -> tuple[list[dict[str, Any]], str]:
    contenu = json.loads(chemin.read_text(encoding="utf-8"))
    articles: list[dict[str, Any]] = contenu["articles"]
    sha = sha_articles(articles)
    if sha != contenu["manifeste"]["sha256"]:
        raise ErreurEnvoi(f"instantané altéré : sha256 {sha} ≠ manifeste")
    return articles, sha


# ---------------------------------------------------------------- envoi


def cumuler(rapports: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        "ingestions": [r["id"] for r in rapports],
        **{
            c: sum(r[c] for r in rapports)
            for c in ("lus", "inseres", "inchanges", "nouvelles_versions")
        },
        "rejets": [x for r in rapports for x in r["rejets"]],
        "quasi_doublons": [x for r in rapports for x in r["quasi_doublons"]],
        "duree_s": round(sum(r["duree_s"] for r in rapports), 3),
    }


def envoyer(
    client: httpx.Client,
    url: str,
    jeton: str,
    articles: Sequence[dict[str, Any]],
    sha: str,
    tracer: Tracer,
) -> dict[str, Any]:
    rapports = []
    for debut in range(0, len(articles), TAILLE_LOT):
        lot = list(articles[debut : debut + TAILLE_LOT])
        with tracer.start_as_current_span("ingest.lot") as span:
            span.set_attribute("ingest.articles", len(lot))
            entetes = {"Authorization": f"Bearer {jeton}"}
            propagate.inject(entetes)  # une seule trace : CLI → gateway → rag
            corps = {
                "collection": "textes_reglementaires",
                "instantane_sha256": sha,
                "articles": lot,
            }
            try:
                reponse = client.post(
                    f"{url.rstrip('/')}/api/ingestions", json=corps, headers=entetes
                )
            except httpx.HTTPError as exc:
                raise ErreurEnvoi(f"API injoignable : {exc!r}") from exc
            if reponse.status_code != 201:
                raise ErreurEnvoi(
                    f"lot {debut // TAILLE_LOT + 1} refusé : HTTP {reponse.status_code} "
                    f"{reponse.text[:300]}"
                )
            rapports.append(reponse.json())
    return cumuler(rapports)


def jeton_api(application: str, variable: str) -> str:
    """Jeton Entra pour ``api://<application>`` : la variable si elle existe (CI), sinon ``az``.

    ``api://<nom>`` est le seul identifiant enregistré par infra/entra.sh (``api://<ID client>``
    échoue avec ``az``) ; c'est aussi celui que demande le job evals de la CI.
    """
    if os.environ.get(variable):
        return os.environ[variable]
    sortie = subprocess.run(
        ["az", "account", "get-access-token", "--scope", f"api://{application}/.default",
         "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    if sortie.returncode != 0 or not sortie.stdout.strip():
        raise ErreurEnvoi(f"aucun jeton pour api://{application} : {variable} ou « az login »")
    return sortie.stdout.strip()


def configurer_traces(url: str, jeton_telemetrie: str | None) -> TracerProvider:
    """Fournisseur propre à la CLI (pas global) : service ``agentinsurflow-ingest``."""
    fournisseur = TracerProvider(
        resource=Resource.create({"service.name": "agentinsurflow-ingest"})
    )
    if jeton_telemetrie:
        exportateur = OTLPSpanExporter(
            endpoint=f"{url.rstrip('/')}/v1/traces",
            headers={"Authorization": f"Bearer {jeton_telemetrie}"},
        )
        fournisseur.add_span_processor(BatchSpanProcessor(exportateur))
    else:
        journal.warning("UNDERWRITING_API_CLIENT_ID absent : traces de la CLI non exportées")
    return fournisseur


# ---------------------------------------------------------------- programme


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--url", default="http://localhost:8000", help="gateway (ou rag en direct)")
    parser.add_argument("--instantane", type=Path, help="rejouer un instantané (saute PISTE)")
    parser.add_argument("--date", default=Date.today().isoformat())
    parser.add_argument("--dossier", type=Path, default=Path("data/raw"))
    parser.add_argument("--preuves", type=Path, default=Path("eval/preuves"))
    parser.add_argument("--environnement", default=os.environ.get("APP_ENV", "local"))
    parser.add_argument(
        "--sans-envoi", action="store_true", help="extraire et sauvegarder seulement"
    )
    return parser.parse_args(argv)


def _instantane(args: argparse.Namespace) -> tuple[list[dict[str, Any]], str, str]:
    if args.instantane:
        articles, sha = lire_instantane(args.instantane)
        return articles, sha, "instantane"
    try:
        cfg = ConfigLegifrance()  # type: ignore[call-arg]
    except ValidationError as exc:
        raise ErreurPiste(
            "LEGIFRANCE_CLIENT_ID / LEGIFRANCE_CLIENT_SECRET manquants (.env)"
        ) from exc
    with nouveau_client() as client:
        articles = extraire(client, cfg, jeton_piste(client, cfg), args.date)
    chemin = sauvegarder_instantane(articles, args.dossier, args.environnement, args.date)
    print(f"✔ instantané {chemin} ({len(articles)} articles)")
    return articles, sha_articles(articles), "extraction"


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(argv)
    fournisseur: TracerProvider | None = None
    try:
        articles, sha, mode = _instantane(args)
        if args.sans_envoi:
            return 0
        jeton = jeton_api("agentinsurflow-rag", "INGESTION_JETON")
        # UNDERWRITING_API_CLIENT_ID posé = underwriting-admin déployé, donc traces exportées
        jeton_telemetrie = (
            jeton_api("agentinsurflow-underwriting", "TELEMETRIE_JETON")
            if os.environ.get("UNDERWRITING_API_CLIENT_ID") or os.environ.get("TELEMETRIE_JETON")
            else None
        )
        fournisseur = configurer_traces(args.url, jeton_telemetrie)
        tracer = fournisseur.get_tracer("agentinsurflow.ingest")
        with nouveau_client() as client, tracer.start_as_current_span("ingest.run") as span:
            span.set_attributes(
                {
                    "ingest.instantane_sha256": sha,
                    "ingest.articles": len(articles),
                    "ingest.mode": mode,
                }
            )
            rapport = envoyer(client, args.url, jeton, articles, sha, tracer)
        args.preuves.mkdir(parents=True, exist_ok=True)
        preuve = args.preuves / f"ingestion-{args.date}-{args.environnement}.json"
        preuve.write_text(
            json.dumps(
                {"instantane_sha256": sha, "mode": mode, **rapport}, ensure_ascii=False, indent=2
            ),
            encoding="utf-8",
        )
        print(f"✔ {rapport['inseres']} insérés, {rapport['inchanges']} inchangés, "
              f"{len(rapport['rejets'])} rejets → {preuve}")  # fmt: skip
        return 0
    except (ErreurPiste, ErreurEnvoi, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"✘ {exc}", file=sys.stderr)
        return 1
    finally:
        if fournisseur is not None:
            fournisseur.shutdown()  # vide le lot de spans ; un échec d'export ne lève pas


if __name__ == "__main__":
    sys.exit(main())
