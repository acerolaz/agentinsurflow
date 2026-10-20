"""Point d'entrée HTTP de rag ; ``agentinsurflow_rag.api:app`` est la cible d'uvicorn."""

from .app import app

__all__ = ["app"]
