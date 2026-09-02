from __future__ import annotations

import shutil
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from agent_server.api.utils import ok
from agent_server.core import db
from agent_server.core.auth import get_current_user
from agent_server.rag.loader import convert_doc_to_docx, load_docx, load_pdf
from agent_server.tools.business_tools import knowledge_manage
from agent_server.tools.schemas import KnowledgeManageInput
from common import constants


router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("")
def list_knowledge(current_user: Annotated[dict, Depends(get_current_user)]):
    """查询列表知识库。

    :param current_user: 函数处理所需的“当前用户”数据，类型为 ``Annotated[dict, Depends(get_current_user)]``。
    :return: 返回查询列表知识库得到的处理结果；具体类型由实际执行分支决定。
    """
    return ok(knowledge_manage(KnowledgeManageInput(action="list"), current_user))


@router.post("/rebuild")
def rebuild_knowledge(current_user: Annotated[dict, Depends(get_current_user)]):
    """重建知识库。

    :param current_user: 函数处理所需的“当前用户”数据，类型为 ``Annotated[dict, Depends(get_current_user)]``。
    :return: 返回重建知识库得到的处理结果；具体类型由实际执行分支决定。
    """
    return ok(knowledge_manage(KnowledgeManageInput(action="rebuild"), current_user))


@router.post("/upload")
def upload_knowledge(file: Annotated[UploadFile, File()], current_user: Annotated[dict, Depends(get_current_user)]):
    """上传知识库。

    :param file: 函数处理所需的“文件”数据，类型为 ``Annotated[UploadFile, File()]``。
    :param current_user: 函数处理所需的“当前用户”数据，类型为 ``Annotated[dict, Depends(get_current_user)]``。
    :return: 返回上传知识库得到的处理结果；具体类型由实际执行分支决定。
    :raises HTTPException: 当代码中对应的校验或操作失败条件成立时抛出。
    """
    knowledge_manage(KnowledgeManageInput(action="list"), current_user)
    filename = Path(file.filename or "").name
    if Path(filename).suffix.lower() not in {".pdf", ".docx", ".doc"}:
        raise HTTPException(status_code=400, detail="unsupported file type")
    target = constants.DATAS_DIR / filename
    with target.open("wb") as handle:
        shutil.copyfileobj(file.file, handle)
    return ok({"source_path": str(target)})


@router.get("/{doc_id}/content")
def get_knowledge_content(doc_id: int, current_user: Annotated[dict, Depends(get_current_user)]):
    """读取已入库文档的原始正文。

    :param doc_id: 文档编号。
    :param current_user: 当前登录用户。
    :return: 返回文档标题和提取后的正文。
    """
    knowledge_manage(KnowledgeManageInput(action="list"), current_user)
    doc = db.get_doc(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")

    source_path = Path(str(doc["source_path"]))
    if not source_path.is_file():
        raise HTTPException(status_code=404, detail="document source not found")

    suffix = source_path.suffix.lower()
    if suffix == ".pdf":
        loaded = load_pdf(source_path, enable_ocr=False)
    elif suffix == ".docx":
        loaded = load_docx(source_path, enable_ocr=False)
    elif suffix == ".doc":
        converted = convert_doc_to_docx(source_path)
        if converted is None:
            raise HTTPException(status_code=422, detail="document conversion failed")
        loaded = load_docx(converted, enable_ocr=False, original_path=source_path)
    else:
        raise HTTPException(status_code=400, detail="unsupported file type")

    return ok(
        {
            "id": doc_id,
            "title": str(doc.get("title") or source_path.name),
            "content": "\n\n".join(block.text for block in loaded.blocks if block.text),
        }
    )


@router.delete("/{doc_id}")
def delete_knowledge(doc_id: int, current_user: Annotated[dict, Depends(get_current_user)]):
    """删除知识库。

    :param doc_id: 函数处理所需的“知识文档`id`”数据，类型为 ``int``。
    :param current_user: 函数处理所需的“当前用户”数据，类型为 ``Annotated[dict, Depends(get_current_user)]``。
    :return: 返回删除知识库得到的处理结果；具体类型由实际执行分支决定。
    :raises HTTPException: 当代码中对应的校验或操作失败条件成立时抛出。
    """
    knowledge_manage(KnowledgeManageInput(action="list"), current_user)
    doc = db.get_doc(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")

    source_path = Path(str(doc["source_path"]))
    try:
        resolved_source = source_path.resolve()
        resolved_datas = constants.DATAS_DIR.resolve()
        resolved_source.relative_to(resolved_datas)
    except ValueError:
        resolved_source = None

    deleted = db.delete_doc(doc_id)
    if resolved_source is not None:
        resolved_source.unlink(missing_ok=True)
    rebuild = knowledge_manage(KnowledgeManageInput(action="rebuild"), current_user)
    return ok({"deleted": deleted, "rebuild": rebuild})
