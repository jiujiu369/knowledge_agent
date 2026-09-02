from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATAS_DIR = Path(os.getenv("DATAS_DIR", str(PROJECT_ROOT / "datas")))
CHROMA_DIR = Path(os.getenv("CHROMA_DIR", str(DATAS_DIR / "chroma")))
SQLITE_DB_PATH = Path(os.getenv("APP_DB_PATH", str(DATAS_DIR / "app.db")))
BGE_MODEL_PATH = Path(os.getenv("BGE_MODEL_PATH", str(PROJECT_ROOT / "models" / "bge-base-zh-v1.5")))
RERANKER_MODEL_PATH = Path(os.getenv("RERANKER_MODEL_PATH", str(PROJECT_ROOT / "models" / "bge-reranker-base")))
VLM_MODEL_DIR = Path(os.getenv("VLM_MODEL_DIR", str(PROJECT_ROOT / "models" / "qwen2.5-vl")))

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {"docs:read", "docs:write", "tickets:read", "tickets:write", "users:manage"},
    "hr": {"docs:read", "tickets:read", "tickets:write"},
    "finance": {"docs:read", "tickets:read", "tickets:write"},
    "ops": {"docs:read", "docs:write", "tickets:read", "tickets:write"},
    "employee": {"docs:read", "tickets:read", "tickets:create"},
}

RAG_SIMILARITY_THRESHOLD = 0.70
RAG_TOP_K = 5
RAG_MAX_CONTEXT_CHARS = 6000

RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_MAX_REQUESTS = 120
