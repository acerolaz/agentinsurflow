"""Point d'entrée HTTP du cluster ; ``agentinsurflow_cluster.api:app`` est la cible d'uvicorn."""

from .app import app

__all__ = ["app"]
