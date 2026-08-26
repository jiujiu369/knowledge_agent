from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


def validate_user_text(value: str) -> str:
    """校验用户文本。

    :param value: 函数处理所需的“`value`”数据，类型为 ``str``。
    :return: 返回校验用户文本得到的结果，返回类型为 ``str``。
    :raises ValueError: 当代码中对应的校验或操作失败条件成立时抛出。
    """
    text = " ".join(value.split())
    if not text:
        raise ValueError("input cannot be blank")
    if len(text) > 2000:
        raise ValueError("input too long")
    if sum(1 for char in text if char.isprintable()) / max(len(text), 1) < 0.85:
        raise ValueError("input contains too many invalid characters")
    return text


class DocRetrieveInput(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=10)

    @field_validator("query")
    @classmethod
    def query_valid(cls, value: str) -> str:
        """查询`valid`。

        :param value: 函数处理所需的“`value`”数据，类型为 ``str``。
        :return: 返回查询`valid`得到的结果，返回类型为 ``str``。
        """
        return validate_user_text(value)


class MatchSimilarTicketInput(BaseModel):
    query: str
    limit: int = Field(default=5, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def query_valid(cls, value: str) -> str:
        """查询`valid`。

        :param value: 函数处理所需的“`value`”数据，类型为 ``str``。
        :return: 返回查询`valid`得到的结果，返回类型为 ``str``。
        """
        return validate_user_text(value)


class CreateConsultTicketInput(BaseModel):
    title: str
    content: str
    answer: str = ""

    @field_validator("title", "content")
    @classmethod
    def text_valid(cls, value: str) -> str:
        """文本`valid`。

        :param value: 函数处理所需的“`value`”数据，类型为 ``str``。
        :return: 返回文本`valid`得到的结果，返回类型为 ``str``。
        """
        return validate_user_text(value)


class QueryTicketListInput(BaseModel):
    status: str | None = None
    mine_only: bool = True


class ExportTicketStatInput(BaseModel):
    format: Literal["json"] = "json"


class KnowledgeManageInput(BaseModel):
    action: Literal["list", "rebuild"] = "list"
