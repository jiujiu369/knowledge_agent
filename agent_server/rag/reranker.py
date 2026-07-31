from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from agent_server.rag.chunker import DocumentChunk


RERANKER_MODEL_PATH = Path(r"F:\code\knowledge_agent\models\bge-reranker-base")
RERANKER_REQUIRED_FILES = ("config.json", "tokenizer_config.json")


def reranker_available() -> bool:
    if not RERANKER_MODEL_PATH.exists():
        return False
    has_required = all((RERANKER_MODEL_PATH / name).exists() for name in RERANKER_REQUIRED_FILES)
    has_weight = any(
        (RERANKER_MODEL_PATH / name).exists()
        for name in ("model.safetensors", "pytorch_model.bin", "model.safetensors.index.json")
    )
    return has_required and has_weight


def reranker_status() -> dict[str, object]:
    available = reranker_available()
    skip_reason = None
    if not available:
        skip_reason = f"未发现完整本地 reranker 模型，跳过 Top-1 提升验证: {RERANKER_MODEL_PATH}"
    return {
        "model_path": str(RERANKER_MODEL_PATH),
        "available": available,
        "enabled": reranker_enabled(),
        "skip_reason": skip_reason,
        "todo": None if available else "下载 bge-reranker-base 到 models\\bge-reranker-base 后再启用 RERANKER_ENABLED=true 验证。",
    }


def reranker_enabled() -> bool:
    value = os.getenv("RERANKER_ENABLED", "false").strip().lower()
    return value in {"1", "true", "yes", "on"} and reranker_available()


@lru_cache(maxsize=1)
def get_reranker_model():
    if not reranker_available():
        raise FileNotFoundError(f"Local reranker model not found: {RERANKER_MODEL_PATH}")
    from sentence_transformers import CrossEncoder

    return CrossEncoder(str(RERANKER_MODEL_PATH), local_files_only=True, trust_remote_code=False)


def rerank(query: str, chunks: list[DocumentChunk]) -> list[tuple[DocumentChunk, float]]:
    if not chunks:
        return []
    if not reranker_enabled():
        return [(chunk, float(chunk.metadata.get("score", 0.0))) for chunk in chunks]

    model = get_reranker_model()
    pairs = [(query, chunk.content) for chunk in chunks]
    scores = model.predict(pairs)
    return sorted(
        [(chunk, float(score)) for chunk, score in zip(chunks, scores, strict=True)],
        key=lambda item: item[1],
        reverse=True,
    )
