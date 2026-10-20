"""Doublures des ports du domaine : les tests ne simulent que les ports, jamais l'infrastructure."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from agentinsurflow_rag.domain.models import (
    ArticlePropre,
    CitationRag,
    Extrait,
    IngestionJournalisee,
)
from agentinsurflow_rag.domain.ports import ErreurEmbeddings, ErreurLLM

# ponytail: liste courte des mots outils français, à compléter si un rejeu bute sur un autre
MOTS_OUTILS = frozenset(
    "a à au aux ce ces d de des du en est et il l la le les leur n ne on ou par pas pour qu que "
    "qui s sa se son sont sur un une y".split()
)


def cosinus(a: list[float], b: list[float]) -> float:
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return sum(x * y for x, y in zip(a, b, strict=True)) / (na * nb) if na and nb else 0.0


def _mots(texte: str) -> set[str]:
    return set(re.findall(r"\w+", texte.lower()))


@dataclass
class _Document:
    id: int
    article: ArticlePropre
    collection: str
    obsolete: bool
    ingere_le: datetime
    extrait_le: date


@dataclass
class _Chunk:
    id: int
    document_id: int
    ordre: int
    texte: str
    vecteur: list[float]


class FakeDepotCorpus:
    """DepotCorpus en mémoire : même contrat que l'adaptateur PostgreSQL, sans base.

    La partie « plein texte » est une approximation (mots communs), la fusion est le vrai RRF.
    """

    def __init__(self) -> None:
        self.documents: list[_Document] = []
        self.chunks: list[_Chunk] = []
        self.journal: list[IngestionJournalisee] = []

    def _doc(self, document_id: int) -> _Document:
        return next(d for d in self.documents if d.id == document_id)

    def _extrait(self, chunk: _Chunk, cos: float | None, score: float) -> Extrait:
        doc = self._doc(chunk.document_id)
        a = doc.article
        citation = CitationRag(
            a.doc_id, a.version, a.article, doc.collection, a.date_debut, a.url_source, chunk.id
        )
        return Extrait(citation, chunk.texte, cos, score)

    def _courants(self, collections: list[str]) -> list[_Chunk]:
        return [
            c
            for c in self.chunks
            if not self._doc(c.document_id).obsolete
            and self._doc(c.document_id).collection in collections
        ]

    async def version_connue(self, doc_id: str, version: str) -> bool:
        return any(
            (d.article.doc_id, d.article.version) == (doc_id, version) for d in self.documents
        )

    async def version_courante(self, doc_id: str) -> tuple[int, str, str] | None:
        for d in self.documents:
            if d.article.doc_id == doc_id and not d.obsolete:
                return d.id, d.article.version, d.article.hash_contenu
        return None

    async def inserer(
        self,
        article: ArticlePropre,
        collection: str,
        chunks: list[str],
        vecteurs: list[list[float]],
        extrait_le: date,
    ) -> None:
        doc = _Document(
            len(self.documents) + 1, article, collection, False, datetime.now(UTC), extrait_le
        )
        self.documents.append(doc)
        for ordre, (texte, vecteur) in enumerate(zip(chunks, vecteurs, strict=True)):
            self.chunks.append(_Chunk(len(self.chunks) + 1, doc.id, ordre, texte, vecteur))

    async def confirmer(self, document_id: int, extrait_le: date) -> None:
        doc = self._doc(document_id)
        doc.extrait_le = max(doc.extrait_le, extrait_le)

    async def marquer_obsolete(self, document_id: int) -> None:
        self._doc(document_id).obsolete = True

    async def voisins(
        self, vecteur: list[float], doc_id: str, seuil: float
    ) -> list[tuple[str, float]]:
        meilleurs: dict[str, float] = {}
        for c in self.chunks:
            doc = self._doc(c.document_id)
            if doc.obsolete or doc.article.doc_id == doc_id:
                continue
            score = cosinus(vecteur, c.vecteur)
            if score > seuil:
                meilleurs[doc.article.doc_id] = max(score, meilleurs.get(doc.article.doc_id, 0.0))
        return sorted(meilleurs.items(), key=lambda kv: -kv[1])

    async def journaliser(self, instantane_sha256: str, rapport: dict[str, Any]) -> int:
        ligne = IngestionJournalisee(
            len(self.journal) + 1, instantane_sha256, datetime.now(UTC), rapport
        )
        self.journal.append(ligne)
        return ligne.id

    async def rechercher_hybride(
        self,
        question: str,
        vecteur: list[float],
        collections: list[str],
        candidats: int,
        k: int,
    ) -> list[Extrait]:
        courants = self._courants(collections)
        vect = sorted(courants, key=lambda c: -cosinus(vecteur, c.vecteur))[:candidats]
        mots = _mots(question)
        communs = [
            c
            for c in courants
            if mots & _mots(f"{self._doc(c.document_id).article.article} {c.texte}")
        ]
        texte = sorted(communs, key=lambda c: -len(mots & _mots(c.texte)))[:candidats]
        scores: dict[int, float] = {}
        for classement in (vect, texte):
            for rang, c in enumerate(classement, start=1):
                scores[c.id] = scores.get(c.id, 0.0) + 1.0 / (60 + rang)
        par_id = {c.id: c for c in courants}
        ordre = sorted(scores, key=lambda i: -scores[i])[:k]
        return [
            self._extrait(par_id[i], cosinus(vecteur, par_id[i].vecteur), scores[i]) for i in ordre
        ]

    async def par_articles(self, articles: list[str], collections: list[str]) -> list[Extrait]:
        return [
            self._extrait(c, None, 0.0)
            for c in self._courants(collections)
            if self._doc(c.document_id).article.article in articles
        ]


class FakeLLM:
    """LLM scripté : rend ``texte``, ou lève ``erreur``. Garde la trace des appels."""

    def __init__(self, texte: str = "Réponse simulée.", *, erreur: ErreurLLM | None = None) -> None:
        self.texte, self.erreur, self.modele = texte, erreur, "fake"
        self.appels: list[tuple[str, str]] = []

    def completer(self, systeme: str, question: str) -> str:
        self.appels.append((systeme, question))
        if self.erreur:
            raise self.erreur
        return self.texte


class FakeEmbeddings:
    """Embeddings déterministes : mots hachés dans ``dim`` dimensions, puis normalisation L2.

    Le cosinus reflète les mots partagés (tests de seuil significatifs) ; jamais le vecteur nul.
    Les mots outils sont ignorés : sur le vrai corpus, « de », « pour », « un »… suffisaient à
    faire passer une question hors corpus au-dessus du seuil (rejeu de l'instantané réel).
    """

    def __init__(self, dim: int = 1536, *, erreur: ErreurEmbeddings | None = None) -> None:
        self.dim, self.erreur, self.modele = dim, erreur, "fake-embeddings"
        self.appels: list[list[str]] = []

    def _vecteur(self, texte: str) -> list[float]:
        vecteur = [0.0] * self.dim
        for mot in re.findall(r"\w+", texte.lower()):
            if mot not in MOTS_OUTILS:
                vecteur[int(hashlib.sha256(mot.encode()).hexdigest(), 16) % self.dim] += 1.0
        if not any(vecteur):
            vecteur[0] = 1.0
        norme = math.sqrt(sum(x * x for x in vecteur))
        return [x / norme for x in vecteur]

    def vectoriser(self, textes: list[str]) -> list[list[float]]:
        self.appels.append(list(textes))
        if self.erreur:
            raise self.erreur
        return [self._vecteur(t) for t in textes]
