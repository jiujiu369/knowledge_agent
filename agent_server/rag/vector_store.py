from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import chromadb
from chromadb.errors import NotFoundError
from chromadb.api.models.Collection import Collection

from agent_server.rag.chunker import DocumentChunk
from agent_server.rag.embed_loader import embed_query, embed_texts
from agent_server.rag.loader import LoadedDocument
from common.constants import CHROMA_DIR


LOGGER = logging.getLogger(__name__)
COLLECTION_NAME = "company_policy_docs"


class VectorStoreUnavailable(RuntimeError):
    pass


class RagVectorStore:
    def __init__(self, persist_dir: str | Path = CHROMA_DIR, collection_name: str = COLLECTION_NAME) -> None:
        """初始化当前对象并保存后续操作所需的状态。

        :param persist_dir: 函数处理所需的“`persist``dir`”数据，类型为 ``str | Path``。
        :param collection_name: 函数处理所需的“`collection``name`”数据，类型为 ``str``。
        :return: 无返回值；函数通过副作用、断言或异常完成其职责。
        """
        self.persist_dir = Path(persist_dir)
        self.collection_name = collection_name
        self._client: Any | None = None
        self._collection: Collection | None = None
        self.last_error: str | None = None

    def collection(self) -> Collection:
        """`collection`。

        :return: 返回`collection`得到的结果，返回类型为 ``Collection``。
        :raises VectorStoreUnavailable: 当代码中对应的校验或操作失败条件成立时抛出。
        """
        if self._collection is not None:
            return self._collection
        try:
            self.persist_dir.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(self.persist_dir))
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            return self._collection
        except Exception as exc:
            self.last_error = str(exc)
            LOGGER.warning("Chroma unavailable: %s", exc)
            raise VectorStoreUnavailable(str(exc)) from exc

    def rebuild(self, documents: list[LoadedDocument], chunks: list[DocumentChunk]) -> None:
        """重建。

        :param documents: 函数处理所需的“`documents`”数据，类型为 ``list[LoadedDocument]``。
        :param chunks: 函数处理所需的“`chunks`”数据，类型为 ``list[DocumentChunk]``。
        :return: 无返回值；函数通过副作用、断言或异常完成其职责。
        :raises VectorStoreUnavailable: 当代码中对应的校验或操作失败条件成立时抛出。
        """
        try:
            self.persist_dir.mkdir(parents=True, exist_ok=True)
            if self._client is None:
                self._client = chromadb.PersistentClient(path=str(self.persist_dir))
            self._collection = None
            try:
                self._client.delete_collection(name=self.collection_name)
            except NotFoundError:
                pass
            self._collection = self._client.create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            self.upsert_chunks(chunks)
        except Exception as exc:
            self.last_error = str(exc)
            LOGGER.warning("Chroma rebuild failed: %s", exc)
            raise VectorStoreUnavailable(str(exc)) from exc

    def upsert_chunks(self, chunks: list[DocumentChunk]) -> None:
        """新增或更新`chunks`。

        :param chunks: 函数处理所需的“`chunks`”数据，类型为 ``list[DocumentChunk]``。
        :return: 无返回值；函数通过副作用、断言或异常完成其职责。
        :raises VectorStoreUnavailable: 当代码中对应的校验或操作失败条件成立时抛出。
        """
        if not chunks:
            return
        try:
            collection = self.collection()
            vectors = embed_texts([chunk.content for chunk in chunks])
            metadatas = [_clean_metadata({"id": chunk.id, **chunk.metadata}) for chunk in chunks]
            collection.upsert(
                ids=[chunk.id for chunk in chunks],
                documents=[chunk.content for chunk in chunks],
                metadatas=metadatas,
                embeddings=vectors,
            )
        except Exception as exc:
            self.last_error = str(exc)
            LOGGER.warning("Chroma upsert failed: %s", exc)
            raise VectorStoreUnavailable(str(exc)) from exc

    def update_document(self, source_path: str, chunks: list[DocumentChunk]) -> None:
        """更新文档。

        :param source_path: 函数处理所需的“源文件路径”数据，类型为 ``str``。
        :param chunks: 函数处理所需的“`chunks`”数据，类型为 ``list[DocumentChunk]``。
        :return: 无返回值；函数通过副作用、断言或异常完成其职责。
        :raises VectorStoreUnavailable: 当代码中对应的校验或操作失败条件成立时抛出。
        """
        try:
            collection = self.collection()
            existing = collection.get(where={"source_path": source_path})
            ids = existing.get("ids") or []
            if ids:
                collection.delete(ids=ids)
            self.upsert_chunks(chunks)
        except Exception as exc:
            self.last_error = str(exc)
            LOGGER.warning("Chroma document update failed: %s", exc)
            raise VectorStoreUnavailable(str(exc)) from exc

    def query(self, query: str, top_k: int = 5) -> list[DocumentChunk]:
        """查询。

        :param query: 用户输入或检索使用的查询文本，类型为 ``str``。
        :param top_k: 函数处理所需的“`top``k`”数据，类型为 ``int``。
        :return: 返回查询得到的结果，返回类型为 ``list[DocumentChunk]``。
        """
        try:
            collection = self.collection()
            if collection.count() == 0:
                return []
            result = collection.query(
                query_embeddings=[embed_query(query)],
                n_results=max(top_k, 1),
                include=["documents", "metadatas", "distances"],
            )
            docs = result.get("documents", [[]])[0]
            metadatas = result.get("metadatas", [[]])[0]
            distances = result.get("distances", [[]])[0]
            chunks: list[DocumentChunk] = []
            for doc, metadata, distance in zip(docs, metadatas, distances, strict=False):
                score = max(0.0, 1.0 - float(distance))
                chunk_metadata = dict(metadata or {})
                chunk_metadata["score"] = score
                chunks.append(
                    DocumentChunk(
                        id=str(chunk_metadata.get("id") or ""),
                        content=str(doc),
                        metadata=chunk_metadata,
                    )
                )
            return chunks
        except Exception as exc:
            self.last_error = str(exc)
            LOGGER.warning("Chroma query failed; keyword fallback can continue: %s", exc)
            return []


def _clean_metadata(metadata: dict[str, Any]) -> dict[str, str | int | float | bool | None]:
    """清理元数据。

    :param metadata: 函数处理所需的“元数据”数据，类型为 ``dict[str, Any]``。
    :return: 返回清理元数据得到的结果，返回类型为 ``dict[str, str | int | float | bool | None]``。
    """
    clean: dict[str, str | int | float | bool | None] = {}
    for key, value in metadata.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            clean[key] = value
        else:
            clean[key] = str(value)
    return clean
