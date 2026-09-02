from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def read_text(path: Path, project_root: Path, errors: list[str]) -> str:
    """读取部署文件；缺失时记录检查错误。"""
    if not path.is_file():
        errors.append(f"missing file: {path.relative_to(project_root)}")
        return ""
    return path.read_text(encoding="utf-8")


def require(text: str, value: str, label: str, errors: list[str]) -> None:
    """确认文本含有指定部署约束。"""
    if value not in text:
        errors.append(f"{label}: missing {value}")


def validate(project_root: Path = PROJECT_ROOT) -> list[str]:
    """返回当前仓库轻量部署配置的全部静态错误。"""
    errors: list[str] = []
    deploy_root = project_root / "deploy"
    env_text = read_text(deploy_root / "knowledge-agent.env.example", project_root, errors)
    api_text = read_text(deploy_root / "systemd" / "knowledge-agent-api.service", project_root, errors)
    web_text = read_text(deploy_root / "systemd" / "knowledge-agent-web.service", project_root, errors)
    requirements_text = read_text(project_root / "requirements-cloud.txt", project_root, errors).lower()

    require(env_text, "AGNES_API_KEY=\n", "environment template", errors)
    for value in (
        "VLM_ENABLED=false",
        "RERANKER_ENABLED=false",
        "DATAS_DIR=/opt/knowledge_agent/datas",
        "APP_DB_PATH=/opt/knowledge_agent/datas/app.db",
        "CHROMA_DIR=/opt/knowledge_agent/datas/chroma",
        "BGE_MODEL_PATH=/opt/knowledge_agent/models/bge-base-zh-v1.5",
        "KNOWLEDGE_AGENT_API_BASE_URL=http://127.0.0.1:8000",
    ):
        require(env_text, value, "environment template", errors)

    for dependency in ("paddlepaddle", "paddleocr", "bitsandbytes", "auto-gptq", "llama-cpp"):
        if dependency in requirements_text:
            errors.append(f"requirements-cloud.txt contains excluded dependency: {dependency}")

    api_command = (
        "ExecStart=/opt/knowledge_agent/.venv/bin/python -m uvicorn "
        "agent_server.main:app --host 127.0.0.1 --port 8000"
    )
    web_command = (
        "ExecStart=/opt/knowledge_agent/.venv/bin/python -m streamlit run web/app.py "
        "--server.address 0.0.0.0 --server.port 8501 --browser.gatherUsageStats false"
    )
    for unit_name, unit_text, command in (
        ("knowledge-agent-api.service", api_text, api_command),
        ("knowledge-agent-web.service", web_text, web_command),
    ):
        require(unit_text, "WorkingDirectory=/opt/knowledge_agent", unit_name, errors)
        require(unit_text, "EnvironmentFile=/opt/knowledge_agent/.env", unit_name, errors)
        require(unit_text, "Restart=on-failure", unit_name, errors)
        require(unit_text, "RestartSec=5", unit_name, errors)
        require(unit_text, command, unit_name, errors)

    require(web_text, "After=network.target knowledge-agent-api.service", "knowledge-agent-web.service", errors)
    if "--host 0.0.0.0" in api_text:
        errors.append("knowledge-agent-api.service must not bind the API to 0.0.0.0")
    return errors


def main() -> int:
    """打印检查结果并返回适合自动化调用的退出码。"""
    errors = validate()
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("DEPLOYMENT_CONFIG_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
