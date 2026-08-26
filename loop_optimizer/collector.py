from __future__ import annotations

import json
from pathlib import Path

from loop_optimizer.models import BadSample, QAEvent
from loop_optimizer.rules import high_frequency_keys, normalize_question, score_event


def load_events(logs_dir: str | Path) -> list[QAEvent]:
    """加载`events`。

    :param logs_dir: 函数处理所需的“`logs``dir`”数据，类型为 ``str | Path``。
    :return: 返回加载`events`得到的结果，返回类型为 ``list[QAEvent]``。
    """
    root = Path(logs_dir)
    events: list[QAEvent] = []
    if not root.exists():
        return events
    for path in sorted(root.glob("*.jsonl")):
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                text = line.strip()
                if not text:
                    continue
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if isinstance(data, dict):
                    event = QAEvent.from_mapping(data, source_file=str(path), line_number=line_number)
                    if event.question:
                        events.append(event)
    return events


def collect_samples(logs_dir: str | Path, frequency_threshold: int = 2) -> list[BadSample]:
    """收集`samples`。

    :param logs_dir: 函数处理所需的“`logs``dir`”数据，类型为 ``str | Path``。
    :param frequency_threshold: 函数处理所需的“`frequency``threshold`”数据，类型为 ``int``。
    :return: 返回收集`samples`得到的结果，返回类型为 ``list[BadSample]``。
    """
    events = load_events(logs_dir)
    high_freq = high_frequency_keys(events, threshold=frequency_threshold)
    samples: list[BadSample] = []
    for event in events:
        scored = score_event(event)
        categories = list(scored.categories)
        if normalize_question(event.question) in high_freq:
            categories.append("high_frequency")
        categories = sorted(set(categories))
        if not categories:
            continue
        samples.append(
            BadSample(
                question=event.question,
                answer=event.answer,
                categories=tuple(categories),
                match_score=scored.match_score,
                risk_score=scored.risk_score,
                retrieval_count=len(event.retrieval),
                source_file=event.source_file,
                line_number=event.line_number,
            )
        )
    return samples
