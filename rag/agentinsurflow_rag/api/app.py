"""API REST de rag : ``GET /health`` et ``POST /api/agent`` ; interface = Swagger UI sur ``/``.

Routes minces : elles traduisent HTTP en appel de cas d'usage et rendent des DTO Pydantic.
"""

from __future__ import annotations

from importlib.metadata import version

from fastapi import FastAPI

from .routes import agent, sante

app = FastAPI(title="AgentInsurFlow", version=version("agentinsurflow-rag"), docs_url="/")
app.include_router(sante.router)
app.include_router(agent.router)
