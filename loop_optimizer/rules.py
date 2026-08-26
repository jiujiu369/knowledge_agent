from __future__ import annotations

import re
from collections import Counter

from loop_optimizer.models import QAEvent, ScoredEvent


LOW_MATCH_THRESHOLD = 0.7
HALLUCINATION_RISK_THRESHOLD = 0.3
FACT_PATTERNS = (
    r"\b(?:TK|工单)[-_\dA-Za-z]+\b",
    r"\d+(?:\.\d+)?\s*(?:元|万元|块)",
    r"第[一二三四五六七八九十百\d]+条",
)


def normalize_question(question: str) -> str:
    """规范化问题。

    :param question: 函数处理所需的“问题”数据，类型为 ``str``。
    :return: 返回规范化问题得到的结果，返回类型为 ``str``。
    """
    return re.sub(r"\s+", "", question).strip().lower()


def max_match_score(event: QAEvent) -> float:
    """`max`匹配计算评分。

    :param event: 需要处理或记录的事件数据，类型为 ``QAEvent``。
    :return: 返回`max`匹配计算评分得到的结果，返回类型为 ``float``。
    """
    scores: list[float] = []
    for item in event.retrieval:
        try:
            scores.append(float(item.get("score", 0.0)))
        except (TypeError, ValueError):
            continue
    return max(scores) if scores else 0.0


def rule_risk_score(event: QAEvent) -> float:
    """`rule``risk`计算评分。

    :param event: 需要处理或记录的事件数据，类型为 ``QAEvent``。
    :return: 返回`rule``risk`计算评分得到的结果，返回类型为 ``float``。
    """
    guardrail_score = event.guardrail.get("risk_score", 0.0)
    try:
        risk = float(guardrail_score)
    except (TypeError, ValueError):
        risk = 0.0

    context = "\n".join(str(item.get("content") or "") for item in event.retrieval)
    checked = 0
    misses = 0
    for pattern in FACT_PATTERNS:
        for value in set(re.findall(pattern, event.answer)):
            checked += 1
            if value not in context:
                misses += 1
    if checked:
        risk = max(risk, misses / checked)
    return round(min(max(risk, 0.0), 1.0), 4)


def score_event(event: QAEvent) -> ScoredEvent:
    """计算评分事件。

    :param event: 需要处理或记录的事件数据，类型为 ``QAEvent``。
    :return: 返回计算评分事件得到的结果，返回类型为 ``ScoredEvent``。
    """
    match_score = round(max_match_score(event), 4)
    risk_score = rule_risk_score(event)
    categories: list[str] = []
    if event.question and match_score < LOW_MATCH_THRESHOLD:
        categories.append("low_match")
    if event.question and risk_score > HALLUCINATION_RISK_THRESHOLD:
        categories.append("hallucination_risk")
    return ScoredEvent(event=event, match_score=match_score, risk_score=risk_score, categories=tuple(categories))


def high_frequency_keys(events: list[QAEvent], threshold: int = 2) -> set[str]:
    """`high``frequency``keys`。

    :param events: 函数处理所需的“`events`”数据，类型为 ``list[QAEvent]``。
    :param threshold: 函数处理所需的“`threshold`”数据，类型为 ``int``。
    :return: 返回`high``frequency``keys`得到的结果，返回类型为 ``set[str]``。
    """
    counter = Counter(normalize_question(event.question) for event in events if normalize_question(event.question))
    return {question for question, count in counter.items() if count >= threshold}
