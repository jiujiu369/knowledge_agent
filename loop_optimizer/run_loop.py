from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from loop_optimizer.collector import collect_samples
from loop_optimizer.filter import aggregate_samples
from loop_optimizer.updater import write_outputs


def llm_eval_enabled() -> bool:
    """大语言模型`eval``enabled`。

    :return: 返回大语言模型`eval``enabled`得到的结果，返回类型为 ``bool``。
    """
    return os.getenv("LLM_EVAL_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def parse_args() -> argparse.Namespace:
    """解析命令行参数。

    :return: 返回解析命令行参数得到的结果，返回类型为 ``argparse.Namespace``。
    """
    parser = argparse.ArgumentParser(description="Generate review-only loop optimization artifacts.")
    parser.add_argument("--logs-dir", default=str(PROJECT_ROOT / "agent_server" / "logs"))
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "loop_optimizer" / "output"))
    parser.add_argument("--frequency-threshold", type=int, default=2)
    return parser.parse_args()


def main() -> int:
    """执行当前模块的主流程并协调各项处理步骤。

    :return: 返回执行当前模块的主流程得到的结果，返回类型为 ``int``。
    """
    args = parse_args()
    samples = collect_samples(args.logs_dir, frequency_threshold=args.frequency_threshold)
    findings = aggregate_samples(samples)
    artifacts = write_outputs(findings, args.output_dir)
    summary = {
        "llm_eval_enabled": llm_eval_enabled(),
        "samples": len(samples),
        "findings": len(findings),
        "bad_sample_csv": str(artifacts.bad_sample_csv),
        "optimize_report_md": str(artifacts.optimize_report_md),
        "prompt_diff_md": str(artifacts.prompt_diff_md),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
