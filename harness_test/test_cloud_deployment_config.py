from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
from pathlib import Path


def test_default_model_paths_are_project_relative():
    from common import constants

    assert constants.BGE_MODEL_PATH == constants.PROJECT_ROOT / "models" / "bge-base-zh-v1.5"
    assert constants.RERANKER_MODEL_PATH == constants.PROJECT_ROOT / "models" / "bge-reranker-base"
    assert constants.VLM_MODEL_DIR == constants.PROJECT_ROOT / "models" / "qwen2.5-vl"


def test_model_paths_can_be_overridden(monkeypatch, tmp_path):
    monkeypatch.setenv("BGE_MODEL_PATH", str(tmp_path / "bge"))
    monkeypatch.setenv("RERANKER_MODEL_PATH", str(tmp_path / "reranker"))
    monkeypatch.setenv("VLM_MODEL_DIR", str(tmp_path / "vlm"))
    from common import constants

    reloaded = importlib.reload(constants)
    assert reloaded.BGE_MODEL_PATH == tmp_path / "bge"
    assert reloaded.RERANKER_MODEL_PATH == tmp_path / "reranker"
    assert reloaded.VLM_MODEL_DIR == tmp_path / "vlm"
    monkeypatch.undo()
    importlib.reload(reloaded)


def test_models_ignore_rule_keeps_common_models_tracked():
    project_root = Path(__file__).resolve().parents[1]
    ignore_rules = (project_root / ".gitignore").read_text(encoding="utf-8").splitlines()
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "common/models/__init__.py"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert "/models/" in ignore_rules
    assert "models/" not in ignore_rules
    assert tracked.returncode == 0, tracked.stderr


def test_ecs_template_is_lightweight_and_contains_no_real_key():
    project_root = Path(__file__).resolve().parents[1]
    text = (project_root / "deploy/knowledge-agent.env.example").read_text(encoding="utf-8")
    requirements = (project_root / "requirements-cloud.txt").read_text(encoding="utf-8").lower()

    assert "VLM_ENABLED=false" in text
    assert "RERANKER_ENABLED=false" in text
    assert "KNOWLEDGE_AGENT_API_BASE_URL=http://127.0.0.1:8000" in text
    assert "AGNES_API_KEY=" in text
    assert "paddlepaddle" not in requirements
    assert "paddleocr" not in requirements
    assert "bitsandbytes" not in requirements


def test_systemd_units_use_isolated_directory_and_ports():
    project_root = Path(__file__).resolve().parents[1]
    api = (project_root / "deploy/systemd/knowledge-agent-api.service").read_text(encoding="utf-8")
    web = (project_root / "deploy/systemd/knowledge-agent-web.service").read_text(encoding="utf-8")

    assert "WorkingDirectory=/opt/knowledge_agent" in api
    assert "--host 127.0.0.1 --port 8000" in api
    assert "User=knowledge-agent" in api
    assert "Group=knowledge-agent" in api
    assert "WorkingDirectory=/opt/knowledge_agent" in web
    assert "--server.address 0.0.0.0 --server.port 8501" in web
    assert "User=knowledge-agent" in web
    assert "Group=knowledge-agent" in web
    assert "Wants=knowledge-agent-api.service" in web


def test_static_checker_accepts_committed_deployment_configuration():
    project_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "scripts/check_deployment_config.py"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "DEPLOYMENT_CONFIG_OK"


def test_static_checker_rejects_public_api_binding(tmp_path):
    from scripts.check_deployment_config import validate

    project_root = Path(__file__).resolve().parents[1]
    shutil.copytree(project_root / "deploy", tmp_path / "deploy")
    shutil.copy2(project_root / "requirements-cloud.txt", tmp_path / "requirements-cloud.txt")
    api_unit = tmp_path / "deploy/systemd/knowledge-agent-api.service"
    api_unit.write_text(
        api_unit.read_text(encoding="utf-8").replace("--host 127.0.0.1", "--host 0.0.0.0"),
        encoding="utf-8",
    )

    errors = validate(tmp_path)

    assert "knowledge-agent-api.service must not bind the API to 0.0.0.0" in errors


def test_static_checker_rejects_nonempty_agnes_api_key(tmp_path):
    from scripts.check_deployment_config import validate

    project_root = Path(__file__).resolve().parents[1]
    shutil.copytree(project_root / "deploy", tmp_path / "deploy")
    shutil.copy2(project_root / "requirements-cloud.txt", tmp_path / "requirements-cloud.txt")
    env_template = tmp_path / "deploy/knowledge-agent.env.example"
    env_template.write_text(
        env_template.read_text(encoding="utf-8").replace("AGNES_API_KEY=\n", "AGNES_API_KEY=real-key\n"),
        encoding="utf-8",
    )

    assert "environment template: AGNES_API_KEY must be empty" in validate(tmp_path)


def test_static_checker_rejects_conflicting_duplicate_dotenv_key(tmp_path):
    from scripts.check_deployment_config import validate

    project_root = Path(__file__).resolve().parents[1]
    shutil.copytree(project_root / "deploy", tmp_path / "deploy")
    shutil.copy2(project_root / "requirements-cloud.txt", tmp_path / "requirements-cloud.txt")
    env_template = tmp_path / "deploy/knowledge-agent.env.example"
    env_template.write_text(
        env_template.read_text(encoding="utf-8") + "VLM_ENABLED=true\n",
        encoding="utf-8",
    )

    assert "environment template: conflicting duplicate key VLM_ENABLED" in validate(tmp_path)


def test_static_checker_does_not_accept_commented_systemd_directive(tmp_path):
    from scripts.check_deployment_config import validate

    project_root = Path(__file__).resolve().parents[1]
    shutil.copytree(project_root / "deploy", tmp_path / "deploy")
    shutil.copy2(project_root / "requirements-cloud.txt", tmp_path / "requirements-cloud.txt")
    api_unit = tmp_path / "deploy/systemd/knowledge-agent-api.service"
    api_unit.write_text(
        api_unit.read_text(encoding="utf-8").replace(
            "WorkingDirectory=/opt/knowledge_agent",
            "# WorkingDirectory=/opt/knowledge_agent",
        ),
        encoding="utf-8",
    )

    assert "knowledge-agent-api.service [Service]: WorkingDirectory must be /opt/knowledge_agent" in validate(tmp_path)


def test_static_checker_does_not_accept_commented_dotenv_key(tmp_path):
    from scripts.check_deployment_config import validate

    project_root = Path(__file__).resolve().parents[1]
    shutil.copytree(project_root / "deploy", tmp_path / "deploy")
    shutil.copy2(project_root / "requirements-cloud.txt", tmp_path / "requirements-cloud.txt")
    env_template = tmp_path / "deploy/knowledge-agent.env.example"
    env_template.write_text(
        env_template.read_text(encoding="utf-8").replace(
            "VLM_ENABLED=false",
            "# VLM_ENABLED=false",
        ),
        encoding="utf-8",
    )

    assert "environment template: VLM_ENABLED must be false" in validate(tmp_path)
