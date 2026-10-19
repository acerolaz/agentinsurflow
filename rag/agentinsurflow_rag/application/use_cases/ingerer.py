"""Ingestion d'un lot d'articles (spec §3.2, ⑤ à ⑩) : nettoyage, dédup, découpage, embeddings,
écriture et rapport. Le lot entier tient dans la transaction de l'appelant : si les embeddings
échouent, ``ErreurEmbeddings`` remonte avant la moindre écriture.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict

from ...domain.corpus import decider, decouper, nettoyer
from ...domain.models import ArticlePropre, QuasiDoublon, RapportIngestion, Rejet
from ...domain.ports import ClientEmbeddings, DepotCorpus

SEUIL_QUASI_DOUBLON = 0.95


async def ingerer(
    depot: DepotCorpus,
    emb: ClientEmbeddings,
    *,
    collection: str,
    instantane_sha256: str,
    articles: Sequence[Mapping[str, object]],
) -> RapportIngestion:
    debut = time.perf_counter()
    rapport = RapportIngestion(lus=len(articles))

    # ⑤ ⑥ validation et nettoyage, article par article ; un doc_id ne compte qu'une fois par lot
    propres: list[ArticlePropre] = []
    vus: set[str] = set()
    for brut in articles:
        resultat = nettoyer(brut)
        if isinstance(resultat, Rejet):
            rapport.rejets.append(resultat)
        elif resultat.doc_id in vus:
            rapport.rejets.append(Rejet(resultat.doc_id, "doublon_dans_le_lot"))
        else:
            vus.add(resultat.doc_id)
            propres.append(resultat)

    # ⑦ dédup : que faut-il (ré)indexer ?
    a_indexer: list[tuple[ArticlePropre, int | None]] = []  # (article, version courante à périmer)
    for art in propres:
        courant = await depot.version_courante(art.doc_id)
        decision = decider(courant[1:] if courant else None, art.version, art.hash_contenu)
        if decision == "inchange":
            rapport.inchanges += 1
        elif decision == "conflit_version":
            rapport.rejets.append(Rejet(art.doc_id, "conflit_version"))
        else:
            a_indexer.append((art, courant[0] if courant else None))

    # ⑧ découpage ; ⑨ embeddings : un seul appel pour le lot, hors de la boucle d'événements
    decoupes = [decouper(art.texte) for art, _ in a_indexer]
    textes = [chunk for chunks in decoupes for chunk in chunks]
    vecteurs = await asyncio.to_thread(emb.vectoriser, textes) if textes else []

    # ⑩ écriture : voisins cherchés avant l'insertion, pour voir aussi le début du lot
    position = 0
    for (art, perime), chunks in zip(a_indexer, decoupes, strict=True):
        vecteurs_art = vecteurs[position : position + len(chunks)]
        position += len(chunks)
        for proche, score in await depot.voisins(vecteurs_art[0], art.doc_id, SEUIL_QUASI_DOUBLON):
            rapport.quasi_doublons.append(QuasiDoublon(art.doc_id, proche, round(score, 4)))
        if perime is not None:
            await depot.marquer_obsolete(perime)
            rapport.nouvelles_versions += 1
        else:
            rapport.inseres += 1
        await depot.inserer(art, collection, chunks, vecteurs_art)

    rapport.duree_s = round(time.perf_counter() - debut, 3)
    contenu = {k: v for k, v in asdict(rapport).items() if k != "id"}
    rapport.id = await depot.journaliser(instantane_sha256, contenu)
    return rapport
