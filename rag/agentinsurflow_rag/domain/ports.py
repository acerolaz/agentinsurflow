"""Ports du domaine (repris de Kaldera, ``llm.py``) : le domaine ne connaît que ces interfaces."""

from __future__ import annotations

from typing import Any, Protocol

from .models import (
    ArticlePropre,
    DocumentTrace,
    EtatCorpus,
    Extrait,
    IngestionJournalisee,
    VueContrat,
)


class ErreurDossiers(Exception):
    """underwriting-admin injoignable ou en erreur, ou jeton On-Behalf-Of refusé."""


class ContratIntrouvable(Exception):
    """Contrat absent ou hors du portefeuille du gestionnaire : même erreur (BOLA, OWASP API1)."""


class DepotDossiers(Protocol):
    """Les dossiers, chez underwriting-admin (seul accès à la base ``dossiers``)."""

    async def lire_contrat(self, numero_contrat: str) -> VueContrat | None: ...


class ErreurLLM(Exception):
    """Le LLM n'a pas répondu à temps, ou le fournisseur a renvoyé une erreur."""


class ErreurEmbeddings(Exception):
    """Le modèle d'embeddings n'a pas répondu, ou le fournisseur a renvoyé une erreur."""


class ClientLLM(Protocol):
    modele: str

    def completer(self, systeme: str, question: str) -> str: ...


class ClientEmbeddings(Protocol):
    modele: str

    def vectoriser(self, textes: list[str]) -> list[list[float]]: ...


class DepotCorpus(Protocol):
    """Le corpus indexé (base ``vecteurs``) ; une instance = une transaction, un compte."""

    # --- ingestion (compte writer)
    async def version_courante(self, doc_id: str) -> tuple[int, str, str] | None:
        """(id, version, hash) de la version non obsolète de l'article, s'il est connu."""
        ...

    async def inserer(
        self,
        article: ArticlePropre,
        collection: str,
        chunks: list[str],
        vecteurs: list[list[float]],
    ) -> None: ...

    async def marquer_obsolete(self, document_id: int) -> None: ...

    async def voisins(
        self, vecteur: list[float], doc_id: str, seuil: float
    ) -> list[tuple[str, float]]:
        """Autres articles courants dont un chunk a un cosinus > ``seuil`` avec ``vecteur``."""
        ...

    async def journaliser(self, instantane_sha256: str, rapport: dict[str, Any]) -> int: ...

    # --- recherche et traçabilité (compte reader)
    async def rechercher_hybride(
        self,
        question: str,
        vecteur: list[float],
        collections: list[str],
        candidats: int,
        k: int,
    ) -> list[Extrait]:
        """Cosinus (HNSW) et plein texte (GIN) fusionnés par RRF (k = 60), meilleur en tête."""
        ...

    async def par_articles(self, articles: list[str], collections: list[str]) -> list[Extrait]: ...

    async def document(self, doc_id: str) -> DocumentTrace | None: ...

    async def ingestions(self, limit: int, offset: int) -> list[IngestionJournalisee]: ...

    async def ingestion(self, id_: int) -> IngestionJournalisee | None: ...

    async def etat(self) -> EtatCorpus: ...
