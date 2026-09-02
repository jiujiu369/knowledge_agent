from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class UserRole(StrEnum):
    ADMIN = "admin"
    HR = "hr"
    FINANCE = "finance"
    OPS = "ops"
    EMPLOYEE = "employee"


class TicketStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class User(BaseModel):
    id: int | None = None
    username: str
    display_name: str | None = None
    role: UserRole = UserRole.EMPLOYEE
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Ticket(BaseModel):
    id: int | None = None
    title: str
    description: str
    requester_id: int | None = None
    assignee_id: int | None = None
    status: TicketStatus = TicketStatus.OPEN
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Doc(BaseModel):
    id: str | None = None
    title: str
    source_path: str
    content_type: str | None = None
    checksum: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RetrievalResult(BaseModel):
    doc_id: str
    content: str
    score: float
    source_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "Doc",
    "RetrievalResult",
    "Ticket",
    "TicketStatus",
    "User",
    "UserRole",
]
