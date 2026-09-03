from __future__ import annotations

import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
README_PATH = PROJECT_ROOT / "README.md"
DEPLOYMENT_PLAN_PATH = (
    PROJECT_ROOT / "docs/superpowers/plans/2026-09-03-cloud-lightweight-deployment.md"
)

DEPLOYMENT_REQUIRED_FRAGMENTS = [
    "chown -R root:knowledge-agent /opt/knowledge_agent/.venv",
    "find /opt/knowledge_agent/.venv -type d -exec chmod 750 {} +",
    "find /opt/knowledge_agent/.venv -type f -exec chmod 640 {} +",
    "find /opt/knowledge_agent/.venv/bin -type f -exec chmod 750 {} +",
    "stat -c '%U:%G %a' /opt/knowledge_agent/.venv",
    "sudo -u knowledge-agent test -x /opt/knowledge_agent/.venv/bin/python",
    "import site; import agent_server.main; import web.app",
    "KNOWLEDGE_AGENT_RAG_PROBE_QUERY",
    "/api/knowledge/rebuild",
    "/api/tools/doc_retrieve",
    "RAG_REAL_PROBE_OK",
    "NRestarts",
    "MemoryCurrent",
    "KERNEL_LOG=",
]

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
    "使用说明书.md",
    "scripts/freshman_run.sh",
    "scripts/bootstrap_admin.py",
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
    "本地全量模式",
    "ECS 轻量模式",
    "bge-base-zh-v1.5",
    "bge-reranker-base",
    "qwen2.5-vl",
    "VLM_ENABLED=false",
    "RERANKER_ENABLED=false",
    "模型、密钥和业务数据不随 Git 提供",
    "PROJECT_ROOT / models / bge-base-zh-v1.5",
    "BGE_MODEL_PATH",
    "Ubuntu 22.04",
    "root:knowledge-agent 640",
    "getpass",
]

REQUIRED_COMMAND_FRAGMENTS = [
    "-m uvicorn agent_server.main:app",
    "-m streamlit run web/app.py",
    "-m pytest harness_test -q",
    "run_harness.py --stress-duration 10s",
    "-m loop_optimizer.run_loop",
    "scripts\\verify_readme.py",
    "systemctl",
    "8501",
    "git clone",
    "python -m venv .venv",
    ".\\.venv\\Scripts\\Activate.ps1",
    ".venv\\Scripts\\python.exe -m pip install -r requirements.txt",
    "Copy-Item .env.example .env",
    "python3.12 -m venv /opt/knowledge_agent/.venv",
    "/opt/knowledge_agent/.venv/bin/python -m pip check",
    "scripts/bootstrap_admin.py",
    "sudo useradd --system",
    "install -o root -g knowledge-agent -m 640",
    "http://127.0.0.1:8501/_stcore/health",
    "NRestarts",
    "MemoryCurrent",
]

FORBIDDEN_PHRASES = [
    "F:\\code\\knowledge_agent",
]


def main() -> int:
    """执行当前模块的主流程并协调各项处理步骤。

    :return: 返回执行当前模块的主流程得到的结果，返回类型为 ``int``。
    """
    failures: list[str] = []
    if not README_PATH.exists():
        failures.append("missing README.md")
        return _finish(failures)

    readme = README_PATH.read_text(encoding="utf-8")
    if not DEPLOYMENT_PLAN_PATH.exists():
        failures.append("missing deployment plan")
        plan = ""
    else:
        plan = DEPLOYMENT_PLAN_PATH.read_text(encoding="utf-8")

    for label, document in (("README", readme), ("Task 6", plan)):
        for fragment in DEPLOYMENT_REQUIRED_FRAGMENTS:
            if fragment not in document:
                failures.append(f"{label} missing deployment fragment: {fragment}")

        initial_marker = document.find("echo 'RAG_LOAD_PHASE=initial'")
        initial_probe = document.find("run_real_rag_probe", initial_marker + 1)
        initial_check = document.find("check_loaded_service_state", initial_marker + 1)
        restart = document.find(
            "systemctl restart knowledge-agent-api.service knowledge-agent-web.service",
            initial_marker + 1,
        )
        post_restart_marker = document.find("echo 'RAG_LOAD_PHASE=post_restart'", restart + 1)
        post_restart_probe = document.find("run_real_rag_probe", post_restart_marker + 1)
        post_restart_check = document.find("check_loaded_service_state", post_restart_marker + 1)
        ordered_positions = (
            ("echo 'RAG_LOAD_PHASE=initial'", initial_marker),
            ("run_real_rag_probe", initial_probe),
            ("check_loaded_service_state", initial_check),
            (
                "systemctl restart knowledge-agent-api.service knowledge-agent-web.service",
                restart,
            ),
            ("echo 'RAG_LOAD_PHASE=post_restart'", post_restart_marker),
            ("run_real_rag_probe", post_restart_probe),
            ("check_loaded_service_state", post_restart_check),
        )
        previous = -1
        for fragment, position in ordered_positions:
            if position <= previous:
                failures.append(
                    f"{label} deployment acceptance order is invalid at: {fragment}"
                )
                break
            previous = position

    for phrase in REQUIRED_PHRASES:
        if phrase not in readme:
            failures.append(f"README missing phrase: {phrase}")

    for fragment in REQUIRED_COMMAND_FRAGMENTS:
        if fragment not in readme:
            failures.append(f"README missing command fragment: {fragment}")

    for phrase in FORBIDDEN_PHRASES:
        if phrase in readme:
            failures.append(f"README contains machine-specific path: {phrase}")

    if "python3 -m venv /opt/knowledge_agent/.venv" in readme:
        failures.append("Ubuntu ECS commands must use python3.12")
    if re.search(r"curl[^\n]*http://127\.0\.0\.1:8501/(?=\s|$)", readme):
        failures.append("README must use Streamlit /_stcore/health")
    if re.search(r"pytest 全量 harness：`\d+ passed", readme):
        failures.append("README must not freeze an easily stale pytest count")

    for relative_path in REQUIRED_PATHS:
        if not (PROJECT_ROOT / relative_path).exists():
            failures.append(f"missing path: {relative_path}")

    python_commands = re.findall(r"\.venv\\Scripts\\python\.exe[^\n`]*", readme)
    if not python_commands:
        failures.append("README has no portable .venv python command")

    return _finish(failures)


def _finish(failures: list[str]) -> int:
    """`finish`。

    :param failures: 函数处理所需的“`failures`”数据，类型为 ``list[str]``。
    :return: 返回`finish`得到的结果，返回类型为 ``int``。
    """
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("README verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
