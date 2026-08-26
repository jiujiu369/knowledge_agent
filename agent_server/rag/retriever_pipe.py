from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import jieba
from rank_bm25 import BM25Okapi

from agent_server.rag.chunker import DocumentChunk, chunk_blocks
from agent_server.rag.loader import load_documents
from agent_server.rag.reranker import rerank, reranker_enabled
from agent_server.rag.vector_store import RagVectorStore
from common.constants import DATAS_DIR, RAG_SIMILARITY_THRESHOLD
from common.models import RetrievalResult


NO_RESULT_MESSAGE = "未检索到足够相关的公司制度片段。"
STOPWORDS = {"什么", "多少", "哪些", "怎么", "如何", "是否", "有哪", "有哪些", "是什么", "一个", "这个", "那个"}


@lru_cache(maxsize=1)
def get_corpus() -> tuple[list[DocumentChunk], list[dict]]:
    """获取检索语料。

    :return: 返回获取检索语料得到的结果，返回类型为 ``tuple[list[DocumentChunk], list[dict]]``。
    """
    documents = load_documents(DATAS_DIR, enable_ocr=True)
    chunks: list[DocumentChunk] = []
    stats: list[dict] = []
    for document in documents:
        doc_chunks = chunk_blocks(document.blocks)
        chunks.extend(doc_chunks)
        stats.append(
            {
                "source_path": document.source_path,
                "chunks": len(doc_chunks),
                "table_blocks": document.table_blocks,
                "image_blocks": document.image_blocks,
            }
        )
    return chunks, stats


def rebuild_index(source_dir: str | Path = DATAS_DIR) -> tuple[list[DocumentChunk], list[dict], str | None]:
    """重建检索索引。

    :param source_dir: 函数处理所需的“源文件`dir`”数据，类型为 ``str | Path``。
    :return: 返回重建检索索引得到的结果，返回类型为 ``tuple[list[DocumentChunk], list[dict], str | None]``。
    """
    documents = load_documents(source_dir, enable_ocr=True)
    chunks: list[DocumentChunk] = []
    stats: list[dict] = []
    for document in documents:
        doc_chunks = chunk_blocks(document.blocks)
        chunks.extend(doc_chunks)
        stats.append(
            {
                "source_path": document.source_path,
                "chunks": len(doc_chunks),
                "table_blocks": document.table_blocks,
                "image_blocks": document.image_blocks,
            }
        )
    store = RagVectorStore()
    error: str | None = None
    try:
        store.rebuild(documents, chunks)
    except Exception as exc:
        error = f"向量库不可用，已保留关键词兜底: {exc}"
    get_corpus.cache_clear()
    _keyword_index.cache_clear()
    return chunks, stats, error


def retrieve(query: str, top_k: int = 5) -> list[RetrievalResult]:
    """检索。

    :param query: 用户输入或检索使用的查询文本，类型为 ``str``。
    :param top_k: 函数处理所需的“`top``k`”数据，类型为 ``int``。
    :return: 返回检索得到的结果，返回类型为 ``list[RetrievalResult]``。
    """
    top_k = max(top_k, 1)
    store = RagVectorStore()
    vector_chunks = store.query(query, top_k=max(top_k * 3, 10))
    candidates = vector_chunks or keyword_search(query, limit=max(top_k * 3, 10))

    if reranker_enabled() and candidates:
        ranked = rerank(query, candidates)
    else:
        ranked = [(chunk, float(chunk.metadata.get("score", 0.0))) for chunk in candidates]

    filtered = _threshold_filter(query, ranked)
    if len(filtered) < top_k:
        existing_ids = {chunk.id for chunk, _ in filtered}
        for chunk in keyword_search(query, limit=top_k * 10):
            if chunk.id in existing_ids:
                continue
            lexical_score = float(chunk.metadata.get("score", 0.0))
            if lexical_score >= _keyword_threshold(query):
                filtered.append((chunk, lexical_score))
                existing_ids.add(chunk.id)
            if len(filtered) >= top_k:
                break

    results = [
        RetrievalResult(
            doc_id=chunk.id,
            content=chunk.content if chunk.content else NO_RESULT_MESSAGE,
            score=round(float(score), 4),
            source_path=str(chunk.metadata.get("source_path") or ""),
            metadata=chunk.metadata,
        )
        for chunk, score in sorted(filtered, key=lambda item: item[1], reverse=True)[:top_k]
    ]
    return results


def keyword_search(query: str, limit: int = 5) -> list[DocumentChunk]:
    """`keyword``search`。

    :param query: 用户输入或检索使用的查询文本，类型为 ``str``。
    :param limit: 函数处理所需的“`limit`”数据，类型为 ``int``。
    :return: 返回`keyword``search`得到的结果，返回类型为 ``list[DocumentChunk]``。
    """
    chunks, _ = get_corpus()
    if not chunks:
        return []
    tokenized, bm25 = _keyword_index()
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    scores = bm25.get_scores(query_tokens)
    ranked: list[DocumentChunk] = []
    max_score = max(scores) if len(scores) else 0
    for index, score in sorted(enumerate(scores), key=lambda item: item[1], reverse=True)[:limit]:
        contains = _contains_score(query, chunks[index].content)
        if contains < _keyword_threshold(query):
            continue
        normalized = (float(score) / float(max_score)) if max_score else 0.0
        final_score = max(normalized * min(1.0, contains * 2), contains)
        if final_score <= 0:
            continue
        metadata = dict(chunks[index].metadata)
        metadata["score"] = min(0.95, final_score)
        metadata["retrieval"] = "keyword"
        ranked.append(DocumentChunk(id=chunks[index].id, content=chunks[index].content, metadata=metadata))
    return ranked


@lru_cache(maxsize=1)
def _keyword_index() -> tuple[list[list[str]], BM25Okapi]:
    """`keyword`检索索引。

    :return: 返回`keyword`检索索引得到的结果，返回类型为 ``tuple[list[list[str]], BM25Okapi]``。
    """
    chunks, _ = get_corpus()
    tokenized = [_tokenize(chunk.content) for chunk in chunks]
    return tokenized, BM25Okapi(tokenized or [[""]])


def _tokenize(text: str) -> list[str]:
    """分词。

    :param text: 需要校验、解析或转换的文本，类型为 ``str``。
    :return: 返回分词得到的结果，返回类型为 ``list[str]``。
    """
    tokens = [token.strip().lower() for token in jieba.lcut(text) if token.strip()]
    tokens.extend(re.findall(r"[a-zA-Z0-9]+", text.lower()))
    return [
        token
        for token in tokens
        if token not in STOPWORDS and (len(token) > 1 or "\u4e00" <= token <= "\u9fff")
    ]


def _contains_score(query: str, content: str) -> float:
    """`contains`计算评分。

    :param query: 用户输入或检索使用的查询文本，类型为 ``str``。
    :param content: 需要处理或写入的文本内容，类型为 ``str``。
    :return: 返回`contains`计算评分得到的结果，返回类型为 ``float``。
    """
    query_terms = [term for term in _tokenize(query) if len(term) >= 2]
    if not query_terms:
        return 0.0
    content_lower = content.lower()
    hits = sum(1 for term in query_terms if term.lower() in content_lower)
    return hits / len(query_terms)


def _threshold_filter(query: str, ranked: list[tuple[DocumentChunk, float]]) -> list[tuple[DocumentChunk, float]]:
    """`threshold`过滤。

    :param query: 用户输入或检索使用的查询文本，类型为 ``str``。
    :param ranked: 函数处理所需的“`ranked`”数据，类型为 ``list[tuple[DocumentChunk, float]]``。
    :return: 返回`threshold`过滤得到的结果，返回类型为 ``list[tuple[DocumentChunk, float]]``。
    """
    filtered: list[tuple[DocumentChunk, float]] = []
    for chunk, score in ranked:
        retrieval = chunk.metadata.get("retrieval")
        if retrieval == "keyword":
            threshold = _keyword_threshold(chunk.content)
            lexical_ok = True
        else:
            threshold = RAG_SIMILARITY_THRESHOLD
            lexical_ok = _contains_score(query, chunk.content) >= 0.1 or score >= 0.86
        if score >= threshold and lexical_ok:
            filtered.append((chunk, score))
    return filtered


def _keyword_threshold(text: str) -> float:
    """`keyword``threshold`。

    :param text: 需要校验、解析或转换的文本，类型为 ``str``。
    :return: 返回`keyword``threshold`得到的结果，返回类型为 ``float``。
    """
    return 0.34 if len(text) > 80 else 0.5
