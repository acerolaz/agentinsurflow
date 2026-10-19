"""API REST de rag : ``GET /health`` et ``POST /api/reponses`` ; Swagger UI sur ``/``.

Routes minces : elles traduisent HTTP en appel de cas d'usage et rendent des DTO Pydantic.
Derrière la gateway, le document est servi en ``/rag/openapi.json`` dans la page Swagger unique ;
il ne déclare pas de ``servers`` : le « Try it out » vise les routes publiques de la gateway.
"""

from __future__ import annotations

from importlib.metadata import version

from fastapi import FastAPI

from .routes import agent, sante

app = FastAPI(title="AgentInsurFlow", version=version("agentinsurflow-rag"), docs_url="/")
app.include_router(sante.router)
app.include_router(agent.router)
