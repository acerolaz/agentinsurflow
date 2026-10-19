"""Client de l'API Légifrance (PISTE, bac à sable) : extraction du Code des assurances,
périmètre auto (S3-2). Sources : client JS SocialGouv (dila-api-client), CGU de l'API.

🔴 Les noms de champs (``cid``, ``num``, ``etat``, ``dateDebut``, ``texteHtml``) et la forme du
plan (``sections`` / ``articles``) sont à confirmer au premier appel réel (Task G0).
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from ...domain.corpus import normaliser_numero

TEXT_ID = "LEGITEXT000006073984"  # Code des assurances
# L121-*, A121-1 (🔴 et son annexe, Task G0), L211-*, R211-*, A211-*
PERIMETRE = re.compile(
    r"^(?:L121-\d+(?:-\d+)*|A121-1|L211-\d+(?:-\d+)*|R211-\d+(?:-\d+)*|A211-\d+(?:-\d+)*)$"
)
DELAIS_S = (1, 2, 4)  # 3 nouvelles tentatives à délai croissant sur 429 et 5xx


class ConfigLegifrance(BaseSettings):
    """Identifiants de l'application PISTE du bac à sable : ``.env`` local seulement."""

    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    legifrance_oauth_url: str = "https://sandbox-oauth.piste.gouv.fr/api/oauth/token"
    legifrance_api_url: str = "https://sandbox-api.piste.gouv.fr/dila/legifrance/lf-engine-app"
    legifrance_client_id: str
    legifrance_client_secret: SecretStr


class ErreurPiste(Exception):
    """PISTE ou Légifrance refuse, ou ne répond pas après les nouvelles tentatives."""


def jeton_piste(client: httpx.Client, cfg: ConfigLegifrance) -> str:
    try:
        reponse = client.post(
            cfg.legifrance_oauth_url,
            data={
                "grant_type": "client_credentials",
                "client_id": cfg.legifrance_client_id,
                "client_secret": cfg.legifrance_client_secret.get_secret_value(),
                "scope": "openid",
            },
        )
    except httpx.HTTPError as exc:
        raise ErreurPiste(f"PISTE injoignable : {exc!r}") from exc
    if reponse.status_code in (400, 401):
        raise ErreurPiste("identifiants PISTE invalides (LEGIFRANCE_CLIENT_ID / _SECRET)")
    if reponse.status_code != 200:
        raise ErreurPiste(f"PISTE a répondu {reponse.status_code}")
    return str(reponse.json()["access_token"])


def appeler(
    client: httpx.Client,
    chemin: str,
    corps: Mapping[str, Any],
    jeton: str,
    *,
    cfg: ConfigLegifrance,
    pause: Callable[[float], object] = time.sleep,
) -> dict[str, Any]:
    url = f"{cfg.legifrance_api_url.rstrip('/')}{chemin}"
    for tentative in range(len(DELAIS_S) + 1):
        try:
            reponse = client.post(url, json=corps, headers={"Authorization": f"Bearer {jeton}"})
            statut = reponse.status_code
        except httpx.TransportError:
            statut = 503  # réseau : même traitement qu'une indisponibilité
            reponse = None
        if statut == 401:
            raise ErreurPiste("identifiants PISTE invalides (jeton refusé par Légifrance)")
        if (statut == 429 or statut >= 500) and tentative < len(DELAIS_S):
            pause(DELAIS_S[tentative])
            continue
        if statut != 200 or reponse is None:
            raise ErreurPiste(f"Légifrance a répondu {statut} sur {chemin}")
        resultat: dict[str, Any] = reponse.json()
        return resultat
    raise AssertionError("inaccessible")  # pragma: no cover


def dans_le_perimetre(numero: str) -> bool:
    return PERIMETRE.match(normaliser_numero(numero)) is not None


def _articles_du_plan(noeud: Mapping[str, Any]) -> Iterator[Mapping[str, Any]]:
    yield from noeud.get("articles") or []
    for section in noeud.get("sections") or []:
        yield from _articles_du_plan(section)


def _date_iso(valeur: object) -> str | None:
    if isinstance(valeur, int | float):  # millisecondes depuis 1970 (🔴 G0)
        return datetime.fromtimestamp(valeur / 1000, tz=UTC).date().isoformat()
    if isinstance(valeur, str) and valeur:
        return valeur[:10]
    return None


def vers_article_entrant(brut: Mapping[str, Any]) -> dict[str, Any]:
    """Article Légifrance → ``ArticleEntrant`` de l'API ; un champ absent reste absent (None)."""
    version = brut.get("id")
    return {
        "doc_id": brut.get("cid"),  # identifiant stable de l'article, toutes versions confondues
        "version": version,  # identifiant de cette version
        "article": brut.get("num"),
        "date_debut": _date_iso(brut.get("dateDebut")),
        "etat": brut.get("etat"),
        "texte_html": brut.get("texteHtml"),
        "url_source": f"https://www.legifrance.gouv.fr/codes/article_lc/{version}"
        if version
        else None,
    }


def extraire(
    client: httpx.Client,
    cfg: ConfigLegifrance,
    jeton: str,
    date: str,
    *,
    pause: Callable[[float], object] = time.sleep,
) -> list[dict[str, Any]]:
    """Plan du code → filtre du périmètre → ``getArticle`` séquentiel (respect des quotas)."""
    plan = appeler(
        client,
        "/consult/code/tableMatieres",
        {"textId": TEXT_ID, "date": date, "nature": "CODE"},
        jeton,
        cfg=cfg,
        pause=pause,
    )
    identifiants = dict.fromkeys(
        str(a["id"])
        for a in _articles_du_plan(plan)
        if a.get("id") and dans_le_perimetre(str(a.get("num", "")))
    )
    articles = []
    for identifiant in identifiants:
        brut = appeler(
            client, "/consult/getArticle", {"id": identifiant}, jeton, cfg=cfg, pause=pause
        )
        articles.append(vers_article_entrant(brut.get("article") or {}))
    return articles
