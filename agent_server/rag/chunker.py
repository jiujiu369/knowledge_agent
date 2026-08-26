from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from agent_server.rag.loader import DocumentBlock


@dataclass(frozen=True)
class DocumentChunk:
    id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


def chunk_blocks(
    blocks: list[DocumentBlock],
    chunk_size: int = 500,
    overlap: int = 50,
) -> list[DocumentChunk]:
    """切分`blocks`。

    :param blocks: 函数处理所需的“`blocks`”数据，类型为 ``list[DocumentBlock]``。
    :param chunk_size: 函数处理所需的“切分`size`”数据，类型为 ``int``。
    :param overlap: 函数处理所需的“`overlap`”数据，类型为 ``int``。
    :return: 返回切分`blocks`得到的结果，返回类型为 ``list[DocumentChunk]``。
    :raises ValueError: 当代码中对应的校验或操作失败条件成立时抛出。
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be >= 0 and smaller than chunk_size")

    chunks: list[DocumentChunk] = []
    for block_index, block in enumerate(blocks):
        text = " ".join(block.text.split()) if block.block_type == "text" else block.text.strip()
        if not text:
            continue

        if block.block_type in {"table", "image"} or len(text) <= chunk_size:
            chunks.append(_make_chunk(block, text, block_index, 0))
            continue

        start = 0
        part_index = 0
        step = chunk_size - overlap
        while start < len(text):
            end = min(start + chunk_size, len(text))
            if end < len(text):
                punctuation = max(text.rfind(mark, start, end) for mark in "。；;？！?!\n")
                if punctuation > start + chunk_size // 2:
                    end = punctuation + 1
            part = text[start:end].strip()
            if part:
                chunks.append(_make_chunk(block, part, block_index, part_index))
                part_index += 1
            if end >= len(text):
                break
            start = max(end - overlap, start + step)
    return chunks


def _make_chunk(block: DocumentBlock, content: str, block_index: int, part_index: int) -> DocumentChunk:
    """创建切分。

    :param block: 函数处理所需的“内容块”数据，类型为 ``DocumentBlock``。
    :param content: 需要处理或写入的文本内容，类型为 ``str``。
    :param block_index: 函数处理所需的“内容块检索索引”数据，类型为 ``int``。
    :param part_index: 函数处理所需的“`part`检索索引”数据，类型为 ``int``。
    :return: 返回创建切分得到的结果，返回类型为 ``DocumentChunk``。
    """
    metadata = {
        "source_path": block.source_path,
        "page": block.page,
        "block_type": block.block_type,
        "block_index": block_index,
        "part_index": part_index,
    }
    metadata.update(block.metadata)
    digest = hashlib.sha1(
        f"{block.source_path}|{block.page}|{block.block_type}|{block_index}|{part_index}|{content}".encode("utf-8")
    ).hexdigest()
    return DocumentChunk(id=digest, content=content, metadata=metadata)
