"""Garde-fous de texte (A2) : LLM Guard + détection de PII française du domaine.

Les scanners sont construits une seule fois (les modèles Hugging Face se chargent à la
construction) ; `entree` et `sortie` ne font que scanner.
"""

from __future__ import annotations

from pathlib import Path

from llm_guard.input_scanners import Anonymize, BanTopics, PromptInjection
from llm_guard.input_scanners import Secrets as SecretsEntree
from llm_guard.input_scanners.ban_topics import MODEL_BGE_M3_V2
from llm_guard.output_scanners import Sensitive
from llm_guard.vault import Vault
from pydantic_settings import BaseSettings, SettingsConfigDict

from agentinsurflow_cluster.domain.pii import pii_detectees

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
        self._injection = PromptInjection(threshold=cfg.seuil_injection)
        self._sujets = BanTopics(
            topics=cfg.sujets(), threshold=cfg.seuil_sujets, model=MODEL_BGE_M3_V2
        )  # multilingue : le modèle par défaut (roberta) laisse passer le français hors sujet
        self._secrets = SecretsEntree()
        # Détection seule : le texte anonymisé n'est jamais utilisé, le Vault est requis par l'API.
        self._anonymize = Anonymize(
            Vault(),
            # sans PERSON : le NER anglais prend « Client fidèle » pour un nom ; les noms ne sont
            # pas détectables de façon fiable en français, e-mail/téléphone/IBAN le sont (domaine).
            entity_types=[
                "CREDIT_CARD",
                "EMAIL_ADDRESS",
                "IBAN_CODE",
                "PHONE_NUMBER",
                "IP_ADDRESS",
            ],
        )
        self._sensible = Sensitive(redact=False)

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
        if not self._anonymize.scan(texte)[1] or pii_detectees(texte):
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
