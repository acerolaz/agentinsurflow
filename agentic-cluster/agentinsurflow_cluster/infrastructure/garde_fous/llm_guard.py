"""Garde-fous de texte (A2) : LLM Guard + détection de PII française du domaine.

Les scanners sont construits une seule fois (les modèles Hugging Face se chargent à la
construction) ; `entree` et `sortie` ne font que scanner.
"""

from __future__ import annotations

from pathlib import Path

from llm_guard.input_scanners import BanTopics, PromptInjection
from llm_guard.input_scanners import Secrets as SecretsEntree
from llm_guard.input_scanners.ban_topics import MODEL_BGE_M3_V2
from llm_guard.output_scanners import Sensitive
from pydantic_settings import BaseSettings, SettingsConfigDict

from agentinsurflow_cluster.domain.pii import pii_detectees

# Entités scannées en entrée ET en sortie : ces 5 seulement (PERSON exclu :
# faux positifs en français) ;
# `pii_detectees` du domaine complète. Tuple : `Sensitive` ajoute « CUSTOM » à la liste reçue.
_ENTITES_PII = ("CREDIT_CARD", "EMAIL_ADDRESS", "IBAN_CODE", "PHONE_NUMBER", "IP_ADDRESS")
_FICHIER = Path(__file__).resolve().parents[3] / "garde_fous.env"


class ConfigGardeFous(BaseSettings):
    model_config = SettingsConfigDict(env_file=_FICHIER, env_ignore_empty=True, extra="ignore")

    seuil_injection: float = 0.9
    seuil_sujets: float = 0.6
    sujets_hors_perimetre: str = ""  # séparés par des virgules

    def sujets(self) -> list[str]:
        return [s.strip() for s in self.sujets_hors_perimetre.split(",") if s.strip()]


class ScannersLlmGuard:
    # PyTorch : `use_onnx` demanderait onnxruntime/optimum, absents des dépendances validées.
    def __init__(self, config: ConfigGardeFous | None = None) -> None:
        cfg = config or ConfigGardeFous()
        sujets = cfg.sujets()
        if not sujets:
            raise ValueError(
                f"sujets_hors_perimetre vide : renseigner SUJETS_HORS_PERIMETRE ou {_FICHIER}"
            )
        # Calibré en T13 : le modèle rend 0 ou 1 (saturé) et juge ~40 % du français légitime
        # (« Le dossier est conforme, prime annuelle calculée ») comme une injection ; aucun seuil
        # < 1 ne l'en empêche, 1.0 couperait la détection. Voir PLAFOND_FAUX_POSITIFS.
        self._injection = PromptInjection(threshold=cfg.seuil_injection)
        self._sujets = BanTopics(
            topics=sujets, threshold=cfg.seuil_sujets, model=MODEL_BGE_M3_V2
        )  # multilingue (roberta par défaut rate le français) ; bge-m3 ≈ 1,1 Go, total ≈ 2,5 Go
        # Secrets() (detect-secrets) ne détecte PAS les clés « sk-… » (OpenAI/Azure).
        self._secrets = SecretsEntree()
        # Détection seule (aucun Vault : il retiendrait les PII en clair pour la vie du processus).
        # Sans PERSON : le NER anglais prend « Client fidèle » pour un nom ; les noms ne sont pas
        # détectables de façon fiable en français, e-mail/téléphone/IBAN le sont (domaine).
        self._sensible = Sensitive(entity_types=list(_ENTITES_PII), redact=False)

    def entree(self, texte: str) -> list[str]:
        codes = [
            code
            for code, scanner in (
                ("prompt_injection", self._injection),
                ("hors_perimetre", self._sujets),
                ("secrets", self._secrets),
            )
            if not scanner.scan(texte)[1]
        ]
        if not self._sensible.scan("", texte)[1] or pii_detectees(texte):
            codes.append("pii")
        return codes

    def sortie(self, texte: str) -> list[str]:
        codes = []
        if not self._sensible.scan("", texte)[1]:
            codes.append("sensible")
        if not self._secrets.scan(texte)[1]:
            codes.append("secrets")
        if pii_detectees(texte):
            codes.append("pii")
        return codes
