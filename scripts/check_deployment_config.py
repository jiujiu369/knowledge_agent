from __future__ import annotations

import sys
from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def read_text(path: Path, project_root: Path, errors: list[str]) -> str:
    """读取部署文件；缺失时记录检查错误。"""
    if not path.is_file():
        errors.append(f"missing file: {path.relative_to(project_root)}")
        return ""
    return path.read_text(encoding="utf-8")


def parse_dotenv(text: str, errors: list[str]) -> dict[str, str]:
    """解析有效的 dotenv 键值并拒绝重复或无效条目。"""
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            errors.append(f"environment template: invalid dotenv line {line_number}")
            continue
        key, value = line.split("=", maxsplit=1)
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            errors.append(f"environment template: invalid key {key!r}")
            continue
        if key in values:
            if values[key] != value:
                errors.append(f"environment template: conflicting duplicate key {key}")
            else:
                errors.append(f"environment template: duplicate key {key}")
            continue
        values[key] = value
    return values


def parse_systemd_unit(text: str, unit_name: str, errors: list[str]) -> dict[str, dict[str, str]]:
    """解析有效的 systemd section/directive，忽略注释行。"""
    sections: dict[str, dict[str, str]] = {}
    current_section: str | None = None
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            current_section = line[1:-1]
            if not current_section:
                errors.append(f"{unit_name}: invalid empty section at line {line_number}")
                continue
            if current_section in sections:
                errors.append(f"{unit_name}: duplicate section [{current_section}]")
                continue
            sections[current_section] = {}
            continue
        if current_section is None or "=" not in line:
            errors.append(f"{unit_name}: invalid directive at line {line_number}")
            continue
        directive, value = line.split("=", maxsplit=1)
        directive = directive.strip()
        if not directive:
            errors.append(f"{unit_name}: invalid directive at line {line_number}")
            continue
        section = sections[current_section]
        if directive in section:
            if section[directive] != value:
                errors.append(
                    f"{unit_name} [{current_section}]: conflicting duplicate directive {directive}"
                )
            else:
                errors.append(f"{unit_name} [{current_section}]: duplicate directive {directive}")
            continue
        section[directive] = value
    return sections


def require_value(
    values: dict[str, str], key: str, expected: str, label: str, errors: list[str]
) -> None:
    """确认解析后的键值等于部署约束。"""
    if values.get(key) != expected:
        errors.append(f"{label}: {key} must be {expected}")


def requirement_names(text: str) -> set[str]:
    """返回 requirements 文件中的有效分发包名。"""
    names: set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name = re.split(r"[<>=!~\[\s]", line, maxsplit=1)[0].lower()
        if name:
            names.add(name)
    return names


def validate(project_root: Path = PROJECT_ROOT) -> list[str]:
    """返回当前仓库轻量部署配置的全部静态错误。"""
    errors: list[str] = []
    deploy_root = project_root / "deploy"
    env_text = read_text(deploy_root / "knowledge-agent.env.example", project_root, errors)
    api_text = read_text(deploy_root / "systemd" / "knowledge-agent-api.service", project_root, errors)
    web_text = read_text(deploy_root / "systemd" / "knowledge-agent-web.service", project_root, errors)
    requirements_text = read_text(project_root / "requirements-cloud.txt", project_root, errors)
    env_values = parse_dotenv(env_text, errors)
    if env_values.get("AGNES_API_KEY") != "":
        errors.append("environment template: AGNES_API_KEY must be empty")
    for key, expected in (
        ("VLM_ENABLED", "false"),
        ("RERANKER_ENABLED", "false"),
        ("DATAS_DIR", "/opt/knowledge_agent/datas"),
        ("APP_DB_PATH", "/opt/knowledge_agent/datas/app.db"),
        ("CHROMA_DIR", "/opt/knowledge_agent/datas/chroma"),
        ("BGE_MODEL_PATH", "/opt/knowledge_agent/models/bge-base-zh-v1.5"),
        ("KNOWLEDGE_AGENT_API_BASE_URL", "http://127.0.0.1:8000"),
    ):
        require_value(env_values, key, expected, "environment template", errors)

    excluded_dependencies = {"paddlepaddle", "paddleocr", "bitsandbytes", "auto-gptq", "llama-cpp"}
    for dependency in sorted(excluded_dependencies.intersection(requirement_names(requirements_text))):
        errors.append(f"requirements-cloud.txt contains excluded dependency: {dependency}")

    api_command = (
        "ExecStart=/opt/knowledge_agent/.venv/bin/python -m uvicorn "
        "agent_server.main:app --host 127.0.0.1 --port 8000"
    )
    web_command = (
        "ExecStart=/opt/knowledge_agent/.venv/bin/python -m streamlit run web/app.py "
        "--server.address 0.0.0.0 --server.port 8501 --browser.gatherUsageStats false"
    )
    api_sections = parse_systemd_unit(api_text, "knowledge-agent-api.service", errors)
    web_sections = parse_systemd_unit(web_text, "knowledge-agent-web.service", errors)
    for unit_name, sections, command in (
        ("knowledge-agent-api.service", api_sections, api_command),
        ("knowledge-agent-web.service", web_sections, web_command),
    ):
        service = sections.get("Service", {})
        for directive, expected in (
            ("WorkingDirectory", "/opt/knowledge_agent"),
            ("EnvironmentFile", "/opt/knowledge_agent/.env"),
            ("User", "knowledge-agent"),
            ("Group", "knowledge-agent"),
            ("Restart", "on-failure"),
            ("RestartSec", "5"),
            ("ExecStart", command.removeprefix("ExecStart=")),
        ):
            require_value(service, directive, expected, f"{unit_name} [Service]", errors)

    require_value(
        web_sections.get("Unit", {}),
        "After",
        "network.target knowledge-agent-api.service",
        "knowledge-agent-web.service [Unit]",
        errors,
    )
    require_value(
        web_sections.get("Unit", {}),
        "Wants",
        "knowledge-agent-api.service",
        "knowledge-agent-web.service [Unit]",
        errors,
    )
    api_command_value = api_sections.get("Service", {}).get("ExecStart", "")
    if "--host 0.0.0.0" in api_command_value:
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
