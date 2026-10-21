"""Point d'entrée HTTP du serveur MCP ; ``agentinsurflow_mcp.api:app`` est la cible d'uvicorn."""

from .app import app

__all__ = ["app"]
