from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent_server.api.auth_router import router as auth_router
from agent_server.api.chat_router import router as chat_router
from agent_server.api.knowledge_router import router as knowledge_router
from agent_server.api.ticket_router import router as ticket_router
from agent_server.api.tool_router import router as tool_router
from agent_server.api.utils import rate_limit_middleware, uniform_exception_middleware
from agent_server.core.db import pool


app = FastAPI(title="Knowledge Agent", version="0.1.0")
app.middleware("http")(uniform_exception_middleware)
app.middleware("http")(rate_limit_middleware)
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(ticket_router)
app.include_router(knowledge_router)
app.include_router(tool_router)


@app.on_event("startup")
def startup() -> None:
    pool()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
