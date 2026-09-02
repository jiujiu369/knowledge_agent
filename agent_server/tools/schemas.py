from __future__ import annotations

from datetime import datetime
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


class LeaveApplicationInput(BaseModel):
    leave_type: Literal["年假", "事假", "病假", "调休", "婚假", "产假/陪产假", "其他"]
    start_at: datetime
    end_at: datetime
    leave_days: float = Field(gt=0)
    reason: str
    request_id: str = Field(min_length=1, max_length=64)

    @field_validator("reason")
    @classmethod
    def reason_valid(cls, value: str) -> str:
        """校验请假原因。

        :param value: 用户填写的请假原因。
        :return: 返回清理后的非空原因。
        """
        return validate_user_text(value)

    @field_validator("end_at")
    @classmethod
    def end_not_before_start(cls, value: datetime, info):
        """校验结束时间不得早于开始时间。

        :param value: 请假结束时间。
        :param info: Pydantic 已校验字段信息。
        :return: 返回校验通过的结束时间。
        """
        start_at = info.data.get("start_at")
        if start_at is not None and value < start_at:
            raise ValueError("end_at cannot be earlier than start_at")
        return value


class QueryTicketListInput(BaseModel):
    status: str | None = None
    mine_only: bool = True


class ExportTicketStatInput(BaseModel):
    format: Literal["json"] = "json"


class KnowledgeManageInput(BaseModel):
    action: Literal["list", "rebuild"] = "list"
