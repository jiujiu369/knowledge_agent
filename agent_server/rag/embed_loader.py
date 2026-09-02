from __future__ import annotations

from functools import lru_cache
import numpy as np
from sentence_transformers import SentenceTransformer

from common.constants import BGE_MODEL_PATH

EXPECTED_EMBEDDING_DIM = 768


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    """获取嵌入模型模型。

    :return: 返回获取嵌入模型模型得到的结果，返回类型为 ``SentenceTransformer``。
    :raises FileNotFoundError: 当代码中对应的校验或操作失败条件成立时抛出。
    :raises ValueError: 当代码中对应的校验或操作失败条件成立时抛出。
    """
    if not BGE_MODEL_PATH.exists():
        raise FileNotFoundError(f"Local BGE model not found: {BGE_MODEL_PATH}")
    model = SentenceTransformer(
        str(BGE_MODEL_PATH),
        local_files_only=True,
        trust_remote_code=False,
    )
    if hasattr(model, "get_embedding_dimension"):
        dimension = int(model.get_embedding_dimension() or 0)
    else:
        dimension = int(model.get_sentence_embedding_dimension() or 0)
    if dimension != EXPECTED_EMBEDDING_DIM:
        raise ValueError(f"BGE embedding dimension must be 768, got {dimension}")
    return model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """生成向量`texts`。

    :param texts: 函数处理所需的“`texts`”数据，类型为 ``list[str]``。
    :return: 返回生成向量`texts`得到的结果，返回类型为 ``list[list[float]]``。
    :raises ValueError: 当代码中对应的校验或操作失败条件成立时抛出。
    """
    if not texts:
        return []
    model = get_embedding_model()
    vectors = model.encode(
        texts,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    array = np.asarray(vectors)
    if array.ndim != 2 or array.shape[1] != EXPECTED_EMBEDDING_DIM:
        raise ValueError(f"Embedding output must be (*, 768), got {array.shape}")
    return array.astype(float).tolist()


def embed_query(query: str) -> list[float]:
    """生成向量查询。

    :param query: 用户输入或检索使用的查询文本，类型为 ``str``。
    :return: 返回生成向量查询得到的结果，返回类型为 ``list[float]``。
    """
    return embed_texts([query])[0]
