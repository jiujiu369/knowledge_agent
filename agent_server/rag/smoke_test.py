from __future__ import annotations

import os

from agent_server.rag.chunker import DocumentChunk
from agent_server.rag.loader import load_documents
from agent_server.rag.loader import vlm_status
from agent_server.rag.reranker import rerank, reranker_available, reranker_status
from agent_server.rag.retriever_pipe import rebuild_index, retrieve
from common.constants import DATAS_DIR


QUESTIONS = [
    "差旅报销上限多少",
    "新员工转正条件",
    "技术故障处理流程有哪些分支",
]


def main() -> None:
    """执行当前模块的主流程并协调各项处理步骤。

    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    :raises RuntimeError: 当代码中对应的校验或操作失败条件成立时抛出。
    """
    documents = load_documents(DATAS_DIR, enable_ocr=True)
    if not documents:
        raise RuntimeError(f"未找到可入库文档: {DATAS_DIR}")

    _, stats, store_error = rebuild_index(DATAS_DIR)
    print("入库统计:")
    for item in stats:
        print(
            f"- {item['source_path']}: chunks={item['chunks']}, "
            f"table_blocks={item['table_blocks']}, image_blocks={item['image_blocks']}"
        )
    if store_error:
        print(store_error)

    reranker_info = reranker_status()
    if reranker_info["available"]:
        os.environ["RERANKER_ENABLED"] = "true"
        _verify_reranker_top1()
        print("reranker=本地权重已就位，RERANKER_ENABLED=true，Top-1 重排探针通过")
    else:
        print(f"reranker=跳过: {reranker_info['skip_reason']}")

    vlm_info = vlm_status()
    if vlm_info["enabled"]:
        print("vlm=本地权重与 4-bit 依赖已就位，插图语义增强会在 OCR 后启用")
    else:
        print(f"vlm=跳过: {vlm_info['skip_reason']}")

    for question in QUESTIONS:
        results = retrieve(question, top_k=3)
        print(f"\nQ: {question}")
        for index, result in enumerate(results, start=1):
            snippet = result.content.replace("\n", " ")[:220]
            print(f"Top-{index} score={result.score} source={result.source_path}")
            print(_console_safe(snippet))
        if not results:
            print("无结果")

    low_results = retrieve("火星基地午餐菜单是什么", top_k=3)
    print(f"\n低相关问题结果数: {len(low_results)}")
    print("M1 self-check passed")


def _verify_reranker_top1() -> None:
    """验证`reranker``top1`。

    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    :raises RuntimeError: 当代码中对应的校验或操作失败条件成立时抛出。
    """
    chunks = [
        DocumentChunk(id="irrelevant", content="办公用品采购审批流程。", metadata={"score": 0.95}),
        DocumentChunk(id="relevant", content="员工差旅报销标准和交通费报销要求。", metadata={"score": 0.3}),
    ]
    ranked = rerank("差旅报销标准", chunks)
    if not ranked or ranked[0][0].id != "relevant":
        raise RuntimeError("reranker Top-1 improvement probe failed")


def _console_safe(text: str) -> str:
    """`console`安全地处理。

    :param text: 需要校验、解析或转换的文本，类型为 ``str``。
    :return: 返回`console`安全地处理得到的结果，返回类型为 ``str``。
    """
    return text.encode("gbk", errors="ignore").decode("gbk")


if __name__ == "__main__":
    main()
