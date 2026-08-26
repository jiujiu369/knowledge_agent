from __future__ import annotations

import csv
from pathlib import Path

from loop_optimizer.models import Finding, OutputArtifacts


def write_outputs(findings: list[Finding], output_dir: str | Path) -> OutputArtifacts:
    """写入`outputs`。

    :param findings: 函数处理所需的“`findings`”数据，类型为 ``list[Finding]``。
    :param output_dir: 函数处理所需的“输出`dir`”数据，类型为 ``str | Path``。
    :return: 返回写入`outputs`得到的结果，返回类型为 ``OutputArtifacts``。
    """
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    bad_sample_csv = root / "bad_sample.csv"
    optimize_report_md = root / "optimize_report.md"
    prompt_diff_md = root / "prompt_diff.md"
    _write_bad_samples(bad_sample_csv, findings)
    optimize_report_md.write_text(_render_report(findings), encoding="utf-8")
    prompt_diff_md.write_text(_render_prompt_diff(findings), encoding="utf-8")
    return OutputArtifacts(
        bad_sample_csv=bad_sample_csv,
        optimize_report_md=optimize_report_md,
        prompt_diff_md=prompt_diff_md,
    )


def _write_bad_samples(path: Path, findings: list[Finding]) -> None:
    """写入`bad``samples`。

    :param path: 目标文件或目录路径，类型为 ``Path``。
    :param findings: 函数处理所需的“`findings`”数据，类型为 ``list[Finding]``。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "question",
                "count",
                "categories",
                "lowest_match_score",
                "worst_risk_score",
                "suggestion",
                "source_files",
            ],
        )
        writer.writeheader()
        for finding in findings:
            writer.writerow(
                {
                    "question": finding.question,
                    "count": finding.count,
                    "categories": "|".join(finding.categories),
                    "lowest_match_score": finding.lowest_match_score,
                    "worst_risk_score": finding.worst_risk_score,
                    "suggestion": finding.suggestion,
                    "source_files": "|".join(finding.source_files),
                }
            )


def _render_report(findings: list[Finding]) -> str:
    """渲染`report`。

    :param findings: 函数处理所需的“`findings`”数据，类型为 ``list[Finding]``。
    :return: 返回渲染`report`得到的结果，返回类型为 ``str``。
    """
    lines = [
        "# Loop 半自动优化建议",
        "",
        "本报告仅用于人工审核，不会自动修改线上 Prompt 或重建生产向量库。",
        "",
        f"- 问题簇数量：{len(findings)}",
        f"- 样本总数：{sum(item.count for item in findings)}",
        "",
        "## 重点样本",
        "",
    ]
    if not findings:
        lines.append("未发现需要优化的低质量样本。")
    for index, finding in enumerate(findings, start=1):
        lines.extend(
            [
                f"### {index}. {finding.question}",
                "",
                f"- 出现次数：{finding.count}",
                f"- 标签：{', '.join(finding.categories)}",
                f"- 最低匹配分：{finding.lowest_match_score}",
                f"- 最高风险分：{finding.worst_risk_score}",
                f"- 建议：{finding.suggestion}",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def _render_prompt_diff(findings: list[Finding]) -> str:
    """渲染提示词`diff`。

    :param findings: 函数处理所需的“`findings`”数据，类型为 ``list[Finding]``。
    :return: 返回渲染提示词`diff`得到的结果，返回类型为 ``str``。
    """
    examples = [finding.question for finding in findings[:5]]
    example_lines = "\n".join(f"+- 低质量样本示例：{question}" for question in examples) or "+- 暂无低质量样本示例。"
    return (
        "# Prompt Diff 建议稿\n\n"
        "以下内容是人工审核用建议，不会被脚本自动应用。\n\n"
        "```diff\n"
        "--- agent_server/graph_flow/prompt_template.py\n"
        "+++ agent_server/graph_flow/prompt_template.py\n"
        "@@ SYSTEM_PROMPT @@\n"
        "+回答前必须检查检索内容是否支持金额、条款号、工单号等事实。\n"
        "+若检索内容不足，应明确说明未检索到足够依据，并建议创建咨询工单。\n"
        f"{example_lines}\n"
        "```\n"
    )
