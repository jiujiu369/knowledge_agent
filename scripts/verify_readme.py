from __future__ import annotations

import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
README_PATH = PROJECT_ROOT / "README.md"

REQUIRED_PATHS = [
    "README.md",
    ".env.example",
    "agent_server/main.py",
    "agent_server/rag/smoke_test.py",
    "web/app.py",
    "web/local_launcher.py",
    "harness_test/results/m4_summary.json",
    "loop_optimizer/run_loop.py",
    "loop_optimizer/output/bad_sample.csv",
    "loop_optimizer/output/optimize_report.md",
    "loop_optimizer/output/prompt_diff.md",
    "docs/architecture.md",
    "docs/api_doc.md",
    "docs/demo_guide.md",
    "docs/resume_point.md",
    "使用说明.md",
    "scripts/freshman_run.sh",
    "scripts/verify_readme.py",
]

REQUIRED_PHRASES = [
    "数据本地不上云",
    "Embedding 本地运行",
    "向量库本地运行",
    "OCR 本地运行",
    "只有 LLM 生成层走云端 API",
    "API key 只走环境变量",
    "主要函数介绍",
    "F:\\code\\knowledge_agent\\.venv\\Scripts\\python.exe",
]

REQUIRED_COMMAND_FRAGMENTS = [
    "-m uvicorn agent_server.main:app",
    "-m streamlit run web/app.py",
    "-m pytest harness_test -q",
    "run_harness.py --stress-duration 10s",
    "-m loop_optimizer.run_loop",
    "scripts\\verify_readme.py",
]


def main() -> int:
    failures: list[str] = []
    if not README_PATH.exists():
        failures.append("missing README.md")
        return _finish(failures)

    readme = README_PATH.read_text(encoding="utf-8")
    for phrase in REQUIRED_PHRASES:
        if phrase not in readme:
            failures.append(f"README missing phrase: {phrase}")

    for fragment in REQUIRED_COMMAND_FRAGMENTS:
        if fragment not in readme:
            failures.append(f"README missing command fragment: {fragment}")

    for relative_path in REQUIRED_PATHS:
        if not (PROJECT_ROOT / relative_path).exists():
            failures.append(f"missing path: {relative_path}")

    python_commands = re.findall(r"F:\\code\\knowledge_agent\\\.venv\\Scripts\\python\.exe[^\n`]*", readme)
    if not python_commands:
        failures.append("README has no .venv python command")

    return _finish(failures)


def _finish(failures: list[str]) -> int:
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("README verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
