from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer


BGE_MODEL_PATH = r"F:\code\knowledge_agent\models\bge-base-zh-v1.5"
EXPECTED_EMBEDDING_DIM = 768


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    model_dir = Path(BGE_MODEL_PATH)
    if not model_dir.exists():
        raise FileNotFoundError(f"Local BGE model not found: {BGE_MODEL_PATH}")
    model = SentenceTransformer(
        BGE_MODEL_PATH,
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
    return embed_texts([query])[0]
