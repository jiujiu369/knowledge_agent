from __future__ import annotations

from collections import defaultdict

from loop_optimizer.models import BadSample, Finding
from loop_optimizer.rules import normalize_question


def aggregate_samples(samples: list[BadSample]) -> list[Finding]:
    grouped: dict[str, list[BadSample]] = defaultdict(list)
    for sample in samples:
        key = normalize_question(sample.question)
        if key:
            grouped[key].append(sample)

    findings: list[Finding] = []
    for group in grouped.values():
        categories = sorted({category for sample in group for category in sample.categories})
        answers = tuple(dict.fromkeys(sample.answer for sample in group if sample.answer))
        source_files = tuple(sorted({sample.source_file for sample in group if sample.source_file}))
        lowest_match = min(sample.match_score for sample in group)
        worst_risk = max(sample.risk_score for sample in group)
        findings.append(
            Finding(
                question=group[0].question,
                count=len(group),
                categories=tuple(categories),
                worst_risk_score=round(worst_risk, 4),
                lowest_match_score=round(lowest_match, 4),
                answers=answers,
                source_files=source_files,
                suggestion=_suggestion(categories),
            )
        )
    findings.sort(key=lambda item: (item.worst_risk_score, item.count, -item.lowest_match_score), reverse=True)
    return findings


def _suggestion(categories: list[str]) -> str:
    if "hallucination_risk" in categories:
        return "强化回答约束：金额、条款、工单号必须来自检索内容；缺依据时要求说明未命中。"
    if "low_match" in categories:
        return "补充知识库同义词或制度片段，并优化检索 query 改写。"
    if "high_frequency" in categories:
        return "将高频问题沉淀为标准问法和示例答案，加入人工审核后的提示词示例。"
    return "人工复核该问题与检索内容。"
