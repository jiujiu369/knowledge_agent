from __future__ import annotations

import os
from functools import lru_cache

from agent_server.rag.chunker import DocumentChunk
from common.constants import RERANKER_MODEL_PATH


RERANKER_REQUIRED_FILES = ("config.json", "tokenizer_config.json")


def reranker_available() -> bool:
    """`reranker``available`。

    :return: 返回`reranker``available`得到的结果，返回类型为 ``bool``。
    """
    if not RERANKER_MODEL_PATH.exists():
        return False
    has_required = all((RERANKER_MODEL_PATH / name).exists() for name in RERANKER_REQUIRED_FILES)
    has_weight = any(
        (RERANKER_MODEL_PATH / name).exists()
        for name in ("model.safetensors", "pytorch_model.bin", "model.safetensors.index.json")
    )
    return has_required and has_weight


def reranker_status() -> dict[str, object]:
    """`reranker`获取状态。

    :return: 返回`reranker`获取状态得到的结果，返回类型为 ``dict[str, object]``。
    """
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
    """`reranker``enabled`。

    :return: 返回`reranker``enabled`得到的结果，返回类型为 ``bool``。
    """
    value = os.getenv("RERANKER_ENABLED", "false").strip().lower()
    return value in {"1", "true", "yes", "on"} and reranker_available()


@lru_cache(maxsize=1)
def get_reranker_model():
    """获取`reranker`模型。

    :return: 返回获取`reranker`模型得到的处理结果；具体类型由实际执行分支决定。
    :raises FileNotFoundError: 当代码中对应的校验或操作失败条件成立时抛出。
    """
    if not reranker_available():
        raise FileNotFoundError(f"Local reranker model not found: {RERANKER_MODEL_PATH}")
    from sentence_transformers import CrossEncoder

    return CrossEncoder(str(RERANKER_MODEL_PATH), local_files_only=True, trust_remote_code=False)


def rerank(query: str, chunks: list[DocumentChunk]) -> list[tuple[DocumentChunk, float]]:
    """重排。

    :param query: 用户输入或检索使用的查询文本，类型为 ``str``。
    :param chunks: 函数处理所需的“`chunks`”数据，类型为 ``list[DocumentChunk]``。
    :return: 返回重排得到的结果，返回类型为 ``list[tuple[DocumentChunk, float]]``。
    """
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
