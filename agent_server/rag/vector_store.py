from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

import chromadb
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
        self.persist_dir = Path(persist_dir)
        self.collection_name = collection_name
        self._client: Any | None = None
        self._collection: Collection | None = None
        self.last_error: str | None = None

    def collection(self) -> Collection:
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
        try:
            if self.persist_dir.exists():
                shutil.rmtree(self.persist_dir)
            self._client = None
            self._collection = None
            self.upsert_chunks(chunks)
        except Exception as exc:
            self.last_error = str(exc)
            LOGGER.warning("Chroma rebuild failed: %s", exc)
            raise VectorStoreUnavailable(str(exc)) from exc

    def upsert_chunks(self, chunks: list[DocumentChunk]) -> None:
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
    clean: dict[str, str | int | float | bool | None] = {}
    for key, value in metadata.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            clean[key] = value
        else:
            clean[key] = str(value)
    return clean
