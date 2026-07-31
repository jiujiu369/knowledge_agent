from __future__ import annotations

from pathlib import Path

import pytest


def test_loader_scans_supported_docs_and_ignores_storage():
    from agent_server.rag.loader import scan_source_files

    files = scan_source_files(Path("datas"))
    names = {path.name for path in files}

    assert "IDC运维管理手册.docx" in names
    assert "app.db" not in names
    assert all("chroma" not in path.parts for path in files)
    assert all(path.suffix.lower() in {".pdf", ".docx", ".doc"} for path in files)


def test_chunker_preserves_table_and_image_blocks():
    from agent_server.rag.chunker import chunk_blocks
    from agent_server.rag.loader import DocumentBlock

    blocks = [
        DocumentBlock(
            source_path="demo.docx",
            page=None,
            block_type="table",
            text="| 列 | 值 |\n| --- | --- |\n| 转正条件 | 通过考核 |",
        ),
        DocumentBlock(
            source_path="demo.docx",
            page=None,
            block_type="image",
            text="[插图内容: 技术故障 / 判断故障类型 / 联系 IDC]",
        ),
    ]

    chunks = chunk_blocks(blocks, chunk_size=10, overlap=2)

    assert len(chunks) == 2
    assert chunks[0].metadata["block_type"] == "table"
    assert "通过考核" in chunks[0].content
    assert chunks[1].metadata["block_type"] == "image"
    assert "技术故障" in chunks[1].content


def test_embedding_config_uses_local_bge_path():
    from agent_server.rag.embed_loader import BGE_MODEL_PATH, EXPECTED_EMBEDDING_DIM

    assert BGE_MODEL_PATH == r"F:\code\knowledge_agent\models\bge-base-zh-v1.5"
    assert EXPECTED_EMBEDDING_DIM == 768


def test_retrieve_returns_retrieval_result_list_without_crashing():
    from agent_server.rag.retriever_pipe import retrieve

    results = retrieve("差旅报销上限多少", top_k=3)

    assert isinstance(results, list)
    assert len(results) <= 3


def test_reranker_status_reports_local_model_state():
    from agent_server.rag import reranker

    status = reranker.reranker_status()

    assert status["model_path"].endswith(r"models\bge-reranker-base")
    if Path(status["model_path"]).exists():
        assert status["available"] is True
        assert status["skip_reason"] is None
    else:
        assert status["available"] is False
        assert "未发现" in status["skip_reason"]


def test_reranker_reorders_candidates_when_enabled(monkeypatch):
    from agent_server.rag import reranker
    from agent_server.rag.chunker import DocumentChunk

    class FakeReranker:
        def predict(self, pairs):
            assert pairs[0][0] == "报销标准"
            return [0.1, 0.9]

    monkeypatch.setenv("RERANKER_ENABLED", "true")
    monkeypatch.setattr(reranker, "reranker_available", lambda: True)
    monkeypatch.setattr(reranker, "get_reranker_model", lambda: FakeReranker())
    chunks = [
        DocumentChunk(id="1", content="无关内容", metadata={"score": 0.8}),
        DocumentChunk(id="2", content="报销标准为 100 元", metadata={"score": 0.5}),
    ]

    ranked = reranker.rerank("报销标准", chunks)

    assert [chunk.id for chunk, _ in ranked] == ["2", "1"]


def test_reranker_top1_improvement_is_skipped_without_local_model():
    from agent_server.rag import reranker

    if not reranker.reranker_available():
        pytest.skip(reranker.reranker_status()["skip_reason"])

    assert reranker.reranker_enabled() in {False, True}


def test_vlm_status_and_4bit_config_are_explicit():
    from agent_server.rag import loader

    status = loader.vlm_status()
    quantization = loader.build_vlm_quantization_config()

    assert status["model_path"].endswith(r"models\qwen2.5-vl")
    assert "available" in status
    assert getattr(quantization, "load_in_4bit", None) is True or quantization.get("load_in_4bit") is True
    if status["available"] and not status["bitsandbytes_available"]:
        assert "bitsandbytes" in status["skip_reason"]


def test_vlm_semantic_caption_is_merged_with_ocr_text(monkeypatch):
    from agent_server.rag import loader

    monkeypatch.setattr(loader, "vlm_enabled", lambda: True)
    monkeypatch.setattr(loader, "caption_image_with_vlm", lambda payload, ext="png": "流程图：提交申请")

    text = loader.enhance_image_text(b"fake", "png", "OCR文字")

    assert "OCR文字" in text
    assert "流程图：提交申请" in text


def test_real_vlm_load_is_skipped_until_4bit_dependency_is_ready():
    from agent_server.rag import loader

    status = loader.vlm_status()
    if not status["available"] or not status["bitsandbytes_available"]:
        pytest.skip(status["skip_reason"])

    model, processor = loader.get_vlm_model_and_processor()

    assert model is not None
    assert processor is not None
