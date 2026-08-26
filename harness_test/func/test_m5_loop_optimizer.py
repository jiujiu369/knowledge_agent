from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    """写入`jsonl`。

    :param path: 目标文件或目录路径，类型为 ``Path``。
    :param rows: 需要写入、转换或聚合的多行数据，类型为 ``list[dict]``。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")


def test_rule_scoring_marks_low_match_and_hallucination_risk():
    """验证`rule``scoring``marks``low`匹配`and``hallucination``risk`。

    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    from loop_optimizer.models import QAEvent
    from loop_optimizer.rules import score_event

    event = QAEvent(
        timestamp="2026-07-31T22:00:00",
        question="差旅报销上限是多少",
        answer="按第99条报销 9999 元。",
        retrieval=[{"content": "差旅报销按实际制度执行。", "score": 0.21, "source_path": "policy.pdf"}],
        guardrail={"risk_score": 0.75},
        tool_events=[],
    )

    scored = score_event(event)

    assert scored.match_score == 0.21
    assert scored.risk_score >= 0.75
    assert "low_match" in scored.categories
    assert "hallucination_risk" in scored.categories


def test_collector_extracts_low_match_hallucination_and_high_frequency(tmp_path):
    """验证`collector``extracts``low`匹配`hallucination``and``high``frequency`。

    :param tmp_path: pytest 为当前测试提供的隔离临时目录；类型由调用方及当前处理场景决定。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    from loop_optimizer.collector import collect_samples

    _write_jsonl(
        tmp_path / "qa_events.jsonl",
        [
            {
                "timestamp": "2026-07-31T22:00:00",
                "question": "差旅报销上限是多少",
                "answer": "未检索到足够相关制度。",
                "retrieval": [{"content": "其他制度", "score": 0.2, "source_path": "a.pdf"}],
                "guardrail": {"risk_score": 0.0},
                "tool_events": [],
            },
            {
                "timestamp": "2026-07-31T22:01:00",
                "question": "差旅报销上限是多少",
                "answer": "按第99条报销 9999 元。",
                "retrieval": [{"content": "报销标准为 100 元。", "score": 0.86, "source_path": "b.pdf"}],
                "guardrail": {"risk_score": 0.8},
                "tool_events": [],
            },
        ],
    )

    samples = collect_samples(tmp_path)
    categories = {category for sample in samples for category in sample.categories}

    assert "low_match" in categories
    assert "hallucination_risk" in categories
    assert "high_frequency" in categories


def test_filter_deduplicates_and_aggregates_samples(tmp_path):
    """验证过滤`deduplicates``and``aggregates``samples`。

    :param tmp_path: pytest 为当前测试提供的隔离临时目录；类型由调用方及当前处理场景决定。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    from loop_optimizer.collector import collect_samples
    from loop_optimizer.filter import aggregate_samples

    _write_jsonl(
        tmp_path / "qa_events.jsonl",
        [
            {"question": " 年假 怎么 申请 ", "answer": "A", "retrieval": [], "guardrail": {"risk_score": 0.0}},
            {"question": "年假怎么申请", "answer": "B", "retrieval": [], "guardrail": {"risk_score": 0.0}},
        ],
    )

    findings = aggregate_samples(collect_samples(tmp_path))

    assert len(findings) == 1
    assert findings[0].count == 2
    assert "high_frequency" in findings[0].categories


def test_updater_writes_review_only_artifacts_and_preserves_prompt(tmp_path):
    """验证`updater``writes``review``only``artifacts``and``preserves`提示词。

    :param tmp_path: pytest 为当前测试提供的隔离临时目录；类型由调用方及当前处理场景决定。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    from loop_optimizer.collector import collect_samples
    from loop_optimizer.filter import aggregate_samples
    from loop_optimizer.updater import write_outputs

    prompt_path = Path("agent_server/graph_flow/prompt_template.py")
    before_hash = hashlib.sha256(prompt_path.read_bytes()).hexdigest()
    _write_jsonl(
        tmp_path / "logs" / "qa_events.jsonl",
        [
            {
                "timestamp": "2026-07-31T22:00:00",
                "question": "报销多久到账",
                "answer": "第99条规定 9999 元。",
                "retrieval": [{"content": "报销审批通过后进入付款流程。", "score": 0.31, "source_path": "finance.pdf"}],
                "guardrail": {"risk_score": 0.9},
                "tool_events": [{"tool": "doc_retrieve", "count": 1}],
            }
        ],
    )

    artifacts = write_outputs(aggregate_samples(collect_samples(tmp_path / "logs")), tmp_path / "out")
    after_hash = hashlib.sha256(prompt_path.read_bytes()).hexdigest()

    assert before_hash == after_hash
    assert artifacts.bad_sample_csv.exists()
    assert artifacts.optimize_report_md.exists()
    assert artifacts.prompt_diff_md.exists()
    assert artifacts.bad_sample_csv.read_text(encoding="utf-8").strip()
    assert "半自动优化建议" in artifacts.optimize_report_md.read_text(encoding="utf-8")
    assert "SYSTEM_PROMPT" in artifacts.prompt_diff_md.read_text(encoding="utf-8")


def test_chat_api_writes_structured_qa_log_without_auth_secret(api_client, tmp_path, monkeypatch):
    """验证处理对话API`writes``structured``qa`记录`without`认证`secret`。

    :param api_client: 隔离测试环境提供的 FastAPI 测试客户端与辅助数据；类型由调用方及当前处理场景决定。
    :param tmp_path: pytest 为当前测试提供的隔离临时目录；类型由调用方及当前处理场景决定。
    :param monkeypatch: pytest 提供的运行时替换与环境变量修改夹具；类型由调用方及当前处理场景决定。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    from harness_test.fixture.app_client import auth_headers
    from common.models import RetrievalResult

    log_path = tmp_path / "qa_events.jsonl"
    monkeypatch.setenv("QA_LOG_PATH", str(log_path))
    monkeypatch.setattr(
        "agent_server.tools.business_tools.retrieve",
        lambda query, top_k=5: [
            RetrievalResult(
                doc_id="doc-1",
                content="报销审批通过后进入付款流程。",
                score=0.88,
                source_path="finance.pdf",
                metadata={},
            )
        ],
    )
    headers = auth_headers(api_client, "alice")

    response = api_client.post("/api/chat", json={"message": "报销多久到账"}, headers=headers)

    assert response.status_code == 200, response.text
    payload = json.loads(log_path.read_text(encoding="utf-8").strip())
    serialized = json.dumps(payload, ensure_ascii=False)
    assert payload["question"] == "报销多久到账"
    assert payload["retrieval"][0]["score"] == 0.88
    assert "Authorization" not in serialized
    assert headers["Authorization"].split(" ", 1)[1] not in serialized
