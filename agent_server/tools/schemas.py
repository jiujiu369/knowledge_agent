from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


def validate_user_text(value: str) -> str:
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
        return validate_user_text(value)


class MatchSimilarTicketInput(BaseModel):
    query: str
    limit: int = Field(default=5, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def query_valid(cls, value: str) -> str:
        return validate_user_text(value)


class CreateConsultTicketInput(BaseModel):
    title: str
    content: str
    answer: str = ""

    @field_validator("title", "content")
    @classmethod
    def text_valid(cls, value: str) -> str:
        return validate_user_text(value)


class QueryTicketListInput(BaseModel):
    status: str | None = None
    mine_only: bool = True


class ExportTicketStatInput(BaseModel):
    format: Literal["json"] = "json"


class KnowledgeManageInput(BaseModel):
    action: Literal["list", "rebuild"] = "list"
