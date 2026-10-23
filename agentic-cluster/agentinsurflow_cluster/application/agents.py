"""Exécution générique d'un agent : référence déterministe, rédaction LLM facultative, garde-fous.

Le LLM ne fait que rédiger : tout ce qu'il renvoie est comparé à la référence (GP/GR/GF/GA) puis
au garde de sortie ; au moindre doute, repli sur la référence et un texte type (D89, R7).
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field, is_dataclass, replace
from datetime import date
from typing import Any, Literal

from agentinsurflow_cluster.domain.balises import DEBUT_BALISE, FIN_BALISE
from agentinsurflow_cluster.domain.garde_fous import ga, gf, gp, gr
from agentinsurflow_cluster.domain.models import (
    EtatDossier,
    Fiche,
    NomAgent,
    Pieces,
    Prime,
    Rapport,
    Risque,
)
from agentinsurflow_cluster.domain.pii import pii_detectees
from agentinsurflow_cluster.domain.ports import (
    AuditPort,
    ErreurOutil,
    GardeTextePort,
    OutilsPort,
    RedactionPort,
)
from agentinsurflow_cluster.domain.references import prime_de, risque_de, verifier_completude
from agentinsurflow_cluster.domain.specs import SPECS

NOT_FOUND = "NOT_FOUND_IN_CORPUS"
HORS_BAREME = "DONNEE_HORS_BAREME"
_ERREURS_REFERENCE = (ErreurOutil, KeyError, TypeError, ValueError)
_ERREURS_SORTIE = (KeyError, TypeError, ValueError)


@dataclass(frozen=True)
class Dependances:
    outils: OutilsPort
    redaction: RedactionPort
    garde: GardeTextePort
    audit: AuditPort
    pieces_exigees: tuple[str, ...] = ("releve_information", "permis")  # P24 : toute formule
    horloge: Callable[[], float] = time.monotonic
    versions_prompt: Mapping[str, str] = field(default_factory=dict)
    trace_id: Callable[[], str] = lambda: ""  # trace OpenTelemetry courante, injectée (hexa ou "")
    budget_global_s: float = 25.0  # garde globale d'une évaluation (§ 4.9)
    reserve_s: float = 2.0


async def executer_agent(
    nom: NomAgent, etat: EtatDossier, jeton: str, deps: Dependances, budget_s: float
) -> Rapport:
    """Rapport de l'agent `nom` ; ne lève jamais pour une panne d'outil, de LLM ou de garde."""
    debut = deps.horloge()
    version = deps.versions_prompt.get(nom, "")
    budget = min(budget_s, SPECS[nom].delai_s)
    try:
        rapport, codes = await _EXECUTEURS[nom](nom, etat, jeton, deps, budget, version)
    except _ERREURS_REFERENCE:  # référence introuvable ou outil refusé : revue humaine
        rapport, codes = Rapport(nom, {}, "repli", "erreur", version), []
    await deps.audit.tracer(
        etat.numero_contrat,
        rapport,
        codes,
        int((deps.horloge() - debut) * 1000),
        empreinte(replace(etat, observations=None)),  # la vue ne porte jamais les observations
    )
    return rapport


Resultat = tuple[Rapport, list[str]]


def empreinte(valeur: object) -> str:
    """SHA-256 d'une valeur (dataclasses comprises) : seule trace d'un contenu dans l'audit."""
    texte = json.dumps(valeur, default=_json, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(texte.encode()).hexdigest()


def _json(valeur: object) -> object:
    return asdict(valeur) if is_dataclass(valeur) and not isinstance(valeur, type) else str(valeur)


async def _rediger(
    nom: NomAgent,
    etat: EtatDossier,
    jeton: str,
    deps: Dependances,
    budget_s: float,
    version: str,
    *,
    vue: dict[str, Any],
    construire: Callable[[dict[str, Any]], Any],
    controler: Callable[[Any], list[str]],
    texte: Callable[[Any], str],
    repli: Any,
    extra: Callable[[dict[str, Any]], dict[str, Any]] = lambda _s: {},
    finaliser: Callable[[Any], Any] = lambda c: c,
) -> Resultat:
    """LLM puis garde-fous ; `repli=None` ⇒ section vide (Rédacteur), sinon section de référence."""
    section = SPECS[nom].section

    def echec(cause: str, codes: list[str]) -> Resultat:
        contenu = {} if repli is None else {section: repli}
        return Rapport(nom, contenu, "repli", cause, version), codes

    if etat.entree_bloquee:
        return echec("entree_bloquee", [])
    sortie = await deps.redaction.rediger(nom, vue, budget_s, jeton)
    if sortie is None:
        return echec("llm_ko", [])
    if "erreur" in sortie:
        return echec("not_found" if sortie["erreur"] == NOT_FOUND else "erreur", [])
    try:
        candidat = construire(sortie)
    except _ERREURS_SORTIE:
        return echec("sortie_invalide", [])
    codes = controler(candidat) or deps.garde.sortie(texte(candidat))
    if codes:
        return echec(f"garde_fou:{codes[0]}", codes)
    contenu = {section: finaliser(candidat), **extra(sortie)}
    return Rapport(nom, contenu, "llm", None, version), []  # type: ignore[arg-type]


def _tuple(sortie: Mapping[str, Any], cle: str, defaut: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sortie.get(cle, defaut))


# --- 📎 Pièces ------------------------------------------------------------------------------


async def _pieces(
    nom: NomAgent, etat: EtatDossier, jeton: str, deps: Dependances, budget_s: float, version: str
) -> Resultat:
    dossier = etat.dossier or {}
    formule: str = dossier["formule"]  # type: ignore[assignment]
    retour = await deps.outils.appeler(
        nom, jeton, "lister_pieces", {"numero_contrat": etat.numero_contrat}
    )
    exigees = {formule: deps.pieces_exigees}
    ref = verifier_completude(
        formule,
        retour["pieces"],
        date.fromisoformat(str(dossier["date_effet"])),
        exigees,
    )
    connues = {*deps.pieces_exigees, *(p["type"] for p in retour["pieces"])}

    def construire(s: dict[str, Any]) -> Pieces:
        return Pieces(
            s.get("statut", ref.statut), _tuple(s, "manquantes", ref.manquantes), s["note"]
        )

    return await _rediger(
        nom, etat, jeton, deps, budget_s, version,
        vue={"statut": ref.statut, "manquantes": list(ref.manquantes),
             "pieces_exigees": list(deps.pieces_exigees)},
        construire=construire,
        controler=lambda c: gp(c, ref, deps.pieces_exigees, connues),
        texte=lambda c: c.note,
        repli=ref,
    )  # fmt: skip


# --- 📏 Analyste ----------------------------------------------------------------------------


def _note_risque(r: Risque) -> str:
    regles = ", ".join(r.regle_ids) or "aucune"
    return f"Risque {r.classe}, score {r.score}, règles {regles}, barème {r.version_bareme}."


async def _analyste(
    nom: NomAgent, etat: EtatDossier, jeton: str, deps: Dependances, budget_s: float, version: str
) -> Resultat:
    try:
        retour = await deps.outils.appeler(
            nom, jeton, "evaluer_risque", {"numero_contrat": etat.numero_contrat}
        )
    except ErreurOutil as e:
        if e.code != HORS_BAREME:
            raise
        limite = Risque(0, "limite", (), "inconnue", "Donnée hors barème : revue humaine requise.")
        return Rapport(nom, {"risque": limite}, "repli", HORS_BAREME, version), []
    ref = risque_de(retour)

    def construire(s: dict[str, Any]) -> Risque:
        return Risque(
            s.get("score", ref.score),
            s.get("classe", ref.classe),
            _tuple(s, "regle_ids", ref.regle_ids),
            s.get("version_bareme", ref.version_bareme),
            s["note"],
        )

    return await _rediger(
        nom, etat, jeton, deps, budget_s, version,
        vue={"score": ref.score, "classe": ref.classe, "regle_ids": list(ref.regle_ids),
             "version_bareme": ref.version_bareme},
        construire=construire,
        controler=lambda c: gr(c, ref),
        texte=lambda c: c.note,
        repli=replace(ref, note=_note_risque(ref)),
    )  # fmt: skip


# --- 💶 Actuaire ----------------------------------------------------------------------------


async def _actuaire(
    nom: NomAgent, etat: EtatDossier, jeton: str, deps: Dependances, budget_s: float, version: str
) -> Resultat:
    retour = await deps.outils.appeler(
        nom, jeton, "calculer_prime", {"numero_contrat": etat.numero_contrat}
    )
    ref = prime_de(retour)
    gabarit = (
        f"Prime annuelle TTC {ref.prime_ttc_annuelle} €, soit {ref.prime_mensuelle} € par mois, "
        f"calculée avec la formule {ref.version_formule}."
    )

    def construire(s: dict[str, Any]) -> Prime:
        return Prime(
            s.get("prime_ttc_annuelle", ref.prime_ttc_annuelle),
            s.get("prime_mensuelle", ref.prime_mensuelle),
            s.get("version_formule", ref.version_formule),
            s["explication"],
        )

    return await _rediger(
        nom, etat, jeton, deps, budget_s, version,
        vue={"prime_ttc_annuelle": ref.prime_ttc_annuelle, "prime_mensuelle": ref.prime_mensuelle,
             "version_formule": ref.version_formule},
        construire=construire,
        controler=lambda c: ga(c, ref),
        texte=lambda c: c.explication,
        repli=replace(ref, explication=gabarit),
        # une fois GA passé, la section porte les chaînes exactes de la référence
        finaliser=lambda c: replace(ref, explication=c.explication),
    )  # fmt: skip


# --- ⚡ Rédacteur ---------------------------------------------------------------------------

_DECISION: Mapping[str, Literal["ACCEPTE", "REFUSE", "REVUE_HUMAINE"]] = {
    "acceptable": "ACCEPTE",
    "refus": "REFUSE",
    "limite": "REVUE_HUMAINE",
}


async def _redacteur(
    nom: NomAgent, etat: EtatDossier, jeton: str, deps: Dependances, budget_s: float, version: str
) -> Resultat:
    risque = etat.risque
    if risque is None:  # le plan n'appelle jamais le Rédacteur sans risque
        raise ValueError("risque absent")
    formule = str((etat.dossier or {}).get("formule", ""))
    sources: list[dict[str, object]] = []

    def construire(s: dict[str, Any]) -> Fiche:
        sources[:] = s.get("sources", [])
        return Fiche(
            s.get("decision", _DECISION[risque.classe]),
            s["contrat_type"],
            s.get("score", risque.score),
            s.get("version_bareme", risque.version_bareme),
            _tuple(s, "regle_ids", risque.regle_ids),
            tuple(s["motifs"]),
            tuple(s["citations"]),
        )

    brut = (etat.observations or "").replace(FIN_BALISE, "")  # pas d'évasion de la balise
    observations = f"{DEBUT_BALISE}{brut}{FIN_BALISE}" if brut else ""
    return await _rediger(
        nom, etat, jeton, deps, budget_s, version,
        vue={"classe": risque.classe, "score": risque.score, "regle_ids": list(risque.regle_ids),
             "version_bareme": risque.version_bareme, "formule": formule,
             "observations": observations},
        construire=construire,
        controler=lambda c: gf(c, risque, sources, formule)
        + (["GF7"] if pii_detectees(c.contrat_type) else []),
        texte=lambda c: "\n".join((c.contrat_type, *c.motifs)),
        repli=None,
        extra=lambda s: {"sources": tuple(s["sources"])},
    )  # fmt: skip


_EXECUTEURS = {
    "pieces": _pieces,
    "analyste": _analyste,
    "redacteur": _redacteur,
    "actuaire": _actuaire,
}
