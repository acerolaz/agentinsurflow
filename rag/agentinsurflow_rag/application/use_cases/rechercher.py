"""Recherche hybride avec porte de pertinence (spec §4.1).

① référence exacte d'article ; ② cosinus + plein texte fusionnés par RRF ; ③ porte :
cosinus max ≥ seuil, ou référence exacte trouvée. Le score RRF ne sert qu'à ordonner.
"""

from __future__ import annotations

import asyncio

from ...domain.corpus import passe_la_porte, references_articles
from ...domain.models import Extrait, ResultatRecherche
from ...domain.ports import ClientEmbeddings, DepotCorpus


async def rechercher(
    depot: DepotCorpus,
    emb: ClientEmbeddings,
    question: str,
    *,
    seuil: float,
    top_k: int,
    candidats: int,
    collections: list[str],
) -> ResultatRecherche:
    if not collections:  # refus par défaut : aucun rôle ne donne accès à une collection
        return ResultatRecherche("NOT_FOUND_IN_CORPUS", seuil, [])

    references = references_articles(question)
    exacts = await depot.par_articles(references, collections) if references else []

    (vecteur,) = await asyncio.to_thread(emb.vectoriser, [question])
    # un vecteur nul rendrait le cosinus indéfini : on ne cherche alors que par le texte exact
    hybrides = (
        await depot.rechercher_hybride(question, vecteur, collections, candidats, top_k)
        if any(vecteur)
        else []
    )
    cosinus_max = max((e.cosinus for e in hybrides if e.cosinus is not None), default=None)

    if not passe_la_porte(cosinus_max, bool(exacts), seuil):
        return ResultatRecherche(
            "NOT_FOUND_IN_CORPUS", seuil, [], cosinus_max, reference_exacte=False
        )

    vus: set[int] = set()
    resultats: list[Extrait] = []
    for extrait in [*exacts, *hybrides]:  # références exactes en tête, puis l'ordre RRF
        if extrait.citation.chunk_id not in vus:
            vus.add(extrait.citation.chunk_id)
            resultats.append(extrait)
    return ResultatRecherche(
        "OK", seuil, resultats[:top_k], cosinus_max, reference_exacte=bool(exacts)
    )
