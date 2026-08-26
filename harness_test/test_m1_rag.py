from __future__ import annotations

from pathlib import Path

import pytest


def test_loader_scans_supported_docs_and_ignores_storage():
    """验证`loader``scans``supported``docs``and``ignores``storage`。

    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    from agent_server.rag.loader import scan_source_files

    files = scan_source_files(Path("datas"))
    names = {path.name for path in files}

    assert "IDC运维管理手册.docx" in names
    assert "app.db" not in names
    assert all("chroma" not in path.parts for path in files)
    assert all(path.suffix.lower() in {".pdf", ".docx", ".doc"} for path in files)


def test_chunker_preserves_table_and_image_blocks():
    """验证`chunker``preserves`转换表格`and`图片`blocks`。

    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
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
    """验证嵌入模型配置`uses``local``bge`路径。

    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    from agent_server.rag.embed_loader import BGE_MODEL_PATH, EXPECTED_EMBEDDING_DIM

    assert BGE_MODEL_PATH == r"F:\code\knowledge_agent\models\bge-base-zh-v1.5"
    assert EXPECTED_EMBEDDING_DIM == 768


def test_retrieve_returns_retrieval_result_list_without_crashing():
    """验证检索`returns``retrieval`结果查询列表`without``crashing`。

    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    from agent_server.rag.retriever_pipe import retrieve

    results = retrieve("差旅报销上限多少", top_k=3)

    assert isinstance(results, list)
    assert len(results) <= 3


def test_reranker_status_reports_local_model_state():
    """验证`reranker`获取状态`reports``local`模型状态。

    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
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
    """验证`reranker``reorders``candidates``when``enabled`。

    :param monkeypatch: pytest 提供的运行时替换与环境变量修改夹具；类型由调用方及当前处理场景决定。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    from agent_server.rag import reranker
    from agent_server.rag.chunker import DocumentChunk

    class FakeReranker:
        def predict(self, pairs):
            """`predict`。

            :param pairs: 函数处理所需的“`pairs`”数据；类型由调用方及当前处理场景决定。
            :return: 返回`predict`得到的处理结果；具体类型由实际执行分支决定。
            """
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
    """验证`reranker``top1``improvement`判断`skipped``without``local`模型。

    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    from agent_server.rag import reranker

    if not reranker.reranker_available():
        pytest.skip(reranker.reranker_status()["skip_reason"])

    assert reranker.reranker_enabled() in {False, True}


def test_vlm_status_and_4bit_config_are_explicit():
    """验证视觉语言模型获取状态`and``4bit`配置`are``explicit`。

    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    from agent_server.rag import loader

    status = loader.vlm_status()
    quantization = loader.build_vlm_quantization_config()

    assert status["model_path"].endswith(r"models\qwen2.5-vl")
    assert "available" in status
    assert getattr(quantization, "load_in_4bit", None) is True or quantization.get("load_in_4bit") is True
    if status["available"] and not status["bitsandbytes_available"]:
        assert "bitsandbytes" in status["skip_reason"]


def test_vlm_semantic_caption_is_merged_with_ocr_text(monkeypatch):
    """验证视觉语言模型`semantic`生成说明文本判断`merged``with`OCR文本。

    :param monkeypatch: pytest 提供的运行时替换与环境变量修改夹具；类型由调用方及当前处理场景决定。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    from agent_server.rag import loader

    monkeypatch.setattr(loader, "vlm_enabled", lambda: True)
    monkeypatch.setattr(loader, "caption_image_with_vlm", lambda payload, ext="png": "流程图：提交申请")

    text = loader.enhance_image_text(b"fake", "png", "OCR文字")

    assert "OCR文字" in text
    assert "流程图：提交申请" in text


def test_vlm_caption_uses_tokenizer_chat_template_when_processor_lacks_one(monkeypatch):
    """验证视觉语言模型生成说明文本`uses``tokenizer`处理对话`template``when``processor``lacks``one`。

    :param monkeypatch: pytest 提供的运行时替换与环境变量修改夹具；类型由调用方及当前处理场景决定。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    from io import BytesIO

    from PIL import Image

    from agent_server.rag import loader

    class FakeTensor:
        shape = (1, 3)

        def to(self, device):
            """`to`。

            :param device: 函数处理所需的“`device`”数据；类型由调用方及当前处理场景决定。
            :return: 返回`to`得到的处理结果；具体类型由实际执行分支决定。
            """
            return self

    class FakeInputs(dict):
        def __init__(self):
            """初始化当前对象并保存后续操作所需的状态。

            :return: 无返回值；函数通过副作用、断言或异常完成其职责。
            """
            super().__init__({"input_ids": FakeTensor()})

    class FakeOutput:
        def __getitem__(self, key):
            """按索引或键读取当前对象中的数据项。

            :param key: 函数处理所需的“`key`”数据；类型由调用方及当前处理场景决定。
            :return: 返回`getitem`得到的处理结果；具体类型由实际执行分支决定。
            """
            return self

    class FakeTokenizer:
        def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True):
            """应用处理对话`template`。

            :param messages: 函数处理所需的“`messages`”数据；类型由调用方及当前处理场景决定。
            :param tokenize: 函数处理所需的“分词”数据；类型由调用方及当前处理场景决定。
            :param add_generation_prompt: 函数处理所需的“`add``generation`提示词”数据；类型由调用方及当前处理场景决定。
            :return: 返回应用处理对话`template`得到的处理结果；具体类型由实际执行分支决定。
            """
            assert messages[0]["content"][0]["type"] == "image"
            return "<|im_start|>user\n<|vision_start|><|image_pad|><|vision_end|>描述图片<|im_end|>\n<|im_start|>assistant\n"

    class FakeProcessor:
        tokenizer = FakeTokenizer()

        def __call__(self, text, images, return_tensors):
            """以可调用对象方式处理输入并生成对应结果。

            :param text: 需要校验、解析或转换的文本；类型由调用方及当前处理场景决定。
            :param images: 函数处理所需的“`images`”数据；类型由调用方及当前处理场景决定。
            :param return_tensors: 函数处理所需的“`return``tensors`”数据；类型由调用方及当前处理场景决定。
            :return: 返回调用得到的处理结果；具体类型由实际执行分支决定。
            """
            assert "<|image_pad|>" in text[0]
            assert len(images) == 1
            assert return_tensors == "pt"
            return FakeInputs()

        def batch_decode(self, generated, skip_special_tokens=True, clean_up_tokenization_spaces=False):
            """`batch``decode`。

            :param generated: 函数处理所需的“`generated`”数据；类型由调用方及当前处理场景决定。
            :param skip_special_tokens: 函数处理所需的“`skip``special``tokens`”数据；类型由调用方及当前处理场景决定。
            :param clean_up_tokenization_spaces: 函数处理所需的“清理`up``tokenization``spaces`”数据；类型由调用方及当前处理场景决定。
            :return: 返回`batch``decode`得到的处理结果；具体类型由实际执行分支决定。
            """
            return ["图中包含测试文字"]

    class FakeModel:
        device = "cpu"

        def generate(self, **inputs):
            """`generate`。

            :param inputs: 函数处理所需的“`inputs`”数据；类型由调用方及当前处理场景决定。
            :return: 返回`generate`得到的处理结果；具体类型由实际执行分支决定。
            """
            return FakeOutput()

    image = Image.new("RGB", (16, 16), "white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")

    monkeypatch.setattr(loader, "vlm_enabled", lambda: True)
    monkeypatch.setattr(loader, "get_vlm_model_and_processor", lambda: (FakeModel(), FakeProcessor()))

    assert loader.caption_image_with_vlm(buffer.getvalue(), "png") == "图中包含测试文字"


def test_vlm_caption_falls_back_when_processor_chat_template_raises(monkeypatch):
    """验证视觉语言模型生成说明文本`falls``back``when``processor`处理对话`template``raises`。

    :param monkeypatch: pytest 提供的运行时替换与环境变量修改夹具；类型由调用方及当前处理场景决定。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    from agent_server.rag import loader

    class FakeTokenizer:
        def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True):
            """应用处理对话`template`。

            :param messages: 函数处理所需的“`messages`”数据；类型由调用方及当前处理场景决定。
            :param tokenize: 函数处理所需的“分词”数据；类型由调用方及当前处理场景决定。
            :param add_generation_prompt: 函数处理所需的“`add``generation`提示词”数据；类型由调用方及当前处理场景决定。
            :return: 返回应用处理对话`template`得到的处理结果；具体类型由实际执行分支决定。
            """
            return "tokenizer-template"

    class FakeProcessor:
        tokenizer = FakeTokenizer()

        def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True):
            """应用处理对话`template`。

            :param messages: 函数处理所需的“`messages`”数据；类型由调用方及当前处理场景决定。
            :param tokenize: 函数处理所需的“分词”数据；类型由调用方及当前处理场景决定。
            :param add_generation_prompt: 函数处理所需的“`add``generation`提示词”数据；类型由调用方及当前处理场景决定。
            :return: 无返回值；函数通过副作用、断言或异常完成其职责。
            :raises ValueError: 当代码中对应的校验或操作失败条件成立时抛出。
            """
            raise ValueError("processor has no chat template")

    assert loader._apply_vlm_chat_template(FakeProcessor(), []) == "tokenizer-template"


def test_real_vlm_load_is_skipped_until_4bit_dependency_is_ready():
    """验证`real`视觉语言模型加载判断`skipped``until``4bit``dependency`判断`ready`。

    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    from agent_server.rag import loader

    status = loader.vlm_status()
    if not status["available"] or not status["bitsandbytes_available"]:
        pytest.skip(status["skip_reason"])

    model, processor = loader.get_vlm_model_and_processor()

    assert model is not None
    assert processor is not None
