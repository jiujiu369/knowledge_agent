from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class QAEvent:
    timestamp: str = ""
    question: str = ""
    answer: str = ""
    retrieval: list[dict[str, Any]] = field(default_factory=list)
    guardrail: dict[str, Any] = field(default_factory=dict)
    tool_events: list[dict[str, Any]] = field(default_factory=list)
    source_file: str = ""
    line_number: int = 0

    @classmethod
    def from_mapping(cls, data: dict[str, Any], source_file: str = "", line_number: int = 0) -> "QAEvent":
        """`from``mapping`。

        :param data: 函数处理所需的“数据”数据，类型为 ``dict[str, Any]``。
        :param source_file: 函数处理所需的“源文件文件”数据，类型为 ``str``。
        :param line_number: 函数处理所需的“`line``number`”数据，类型为 ``int``。
        :return: 返回`from``mapping`得到的结果，返回类型为 ``'QAEvent'``。
        """
        retrieval = data.get("retrieval") or []
        if not isinstance(retrieval, list):
            retrieval = []
        guardrail = data.get("guardrail") or {}
        if not isinstance(guardrail, dict):
            guardrail = {}
        tool_events = data.get("tool_events") or []
        if not isinstance(tool_events, list):
            tool_events = []
        return cls(
            timestamp=str(data.get("timestamp") or data.get("created_at") or ""),
            question=str(data.get("question") or data.get("message") or ""),
            answer=str(data.get("answer") or ""),
            retrieval=[item for item in retrieval if isinstance(item, dict)],
            guardrail=guardrail,
            tool_events=[item for item in tool_events if isinstance(item, dict)],
            source_file=source_file,
            line_number=line_number,
        )


@dataclass(frozen=True)
class ScoredEvent:
    event: QAEvent
    match_score: float
    risk_score: float
    categories: tuple[str, ...]


@dataclass(frozen=True)
class BadSample:
    question: str
    answer: str
    categories: tuple[str, ...]
    match_score: float
    risk_score: float
    retrieval_count: int
    source_file: str
    line_number: int


@dataclass(frozen=True)
class Finding:
    question: str
    count: int
    categories: tuple[str, ...]
    worst_risk_score: float
    lowest_match_score: float
    answers: tuple[str, ...]
    source_files: tuple[str, ...]
    suggestion: str


@dataclass(frozen=True)
class OutputArtifacts:
    bad_sample_csv: Any
    optimize_report_md: Any
    prompt_diff_md: Any
