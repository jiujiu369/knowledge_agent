from __future__ import annotations

from types import SimpleNamespace


def test_rebuild_index_twice_replaces_collection_and_remains_queryable(tmp_path, monkeypatch, caplog):
    """验证同一进程连续重建会替换旧集合，并保持向量查询可用。

    :param tmp_path: pytest 提供的隔离临时目录。
    :param monkeypatch: pytest 提供的运行时替换夹具。
    :param caplog: pytest 提供的日志捕获夹具。
    :return: 无返回值；通过断言验证连续重建行为。
    """
    from agent_server.rag import retriever_pipe, vector_store
    from agent_server.rag.chunker import DocumentChunk

    persist_dir = tmp_path / "chroma"
    old_chunk = DocumentChunk(id="old", content="旧制度内容", metadata={"source_path": "old.docx"})
    new_chunk = DocumentChunk(id="new", content="新制度内容", metadata={"source_path": "new.docx"})
    rebuild_chunks = iter([[old_chunk], [new_chunk]])
    document = SimpleNamespace(
        blocks=[],
        source_path="fixture.docx",
        table_blocks=0,
        image_blocks=0,
    )

    monkeypatch.setattr(retriever_pipe, "load_documents", lambda source_dir, enable_ocr: [document])
    monkeypatch.setattr(retriever_pipe, "chunk_blocks", lambda blocks: next(rebuild_chunks))
    monkeypatch.setattr(
        retriever_pipe,
        "RagVectorStore",
        lambda: vector_store.RagVectorStore(persist_dir=persist_dir),
    )
    monkeypatch.setattr(vector_store, "embed_texts", lambda texts: [[0.0, 1.0] for _ in texts])
    monkeypatch.setattr(vector_store, "embed_query", lambda query: [0.0, 1.0])

    _, _, first_error = retriever_pipe.rebuild_index(tmp_path)
    _, _, second_error = retriever_pipe.rebuild_index(tmp_path)

    assert first_error is None
    assert second_error is None
    assert "readonly database" not in caplog.text.lower()

    store = vector_store.RagVectorStore(persist_dir=persist_dir)
    collection_data = store.collection().get()
    assert collection_data["ids"] == ["new"]
    assert store.query("新制度", top_k=1)[0].id == "new"


def test_rebuild_creates_collection_when_it_does_not_exist(tmp_path, monkeypatch):
    """验证首次重建时集合不存在也能正常创建。

    :param tmp_path: pytest 提供的隔离临时目录。
    :param monkeypatch: pytest 提供的运行时替换夹具。
    :return: 无返回值；通过断言验证集合创建行为。
    """
    from agent_server.rag import vector_store
    from agent_server.rag.chunker import DocumentChunk

    chunk = DocumentChunk(id="first", content="首次内容", metadata={"source_path": "first.docx"})
    monkeypatch.setattr(vector_store, "embed_texts", lambda texts: [[1.0, 0.0] for _ in texts])

    store = vector_store.RagVectorStore(persist_dir=tmp_path / "chroma")
    store.rebuild([], [chunk])

    assert store.collection().get()["ids"] == ["first"]
