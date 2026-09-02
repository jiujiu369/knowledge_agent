from __future__ import annotations

import ast
import importlib
import re
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_IMPORTS = {"agent_server", "common", "loop_optimizer", "scripts", "web"}
IMPORT_DISTRIBUTIONS = {
    "PIL": "pillow",
    "docx": "python-docx",
    "dotenv": "python-dotenv",
    "fitz": "pymupdf",
    "rank_bm25": "rank-bm25",
    "sentence_transformers": "sentence-transformers",
}


def _requirement_names(path: Path) -> set[str]:
    """解析 requirements 文件中的规范化分发包名。

    :param path: 待解析的 requirements 文件路径。
    :return: 返回统一使用连字符的小写分发包名集合。
    """
    names: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name = re.split(r"[<>=!~\[\s]", line, maxsplit=1)[0]
        names.add(re.sub(r"[-_.]+", "-", name).lower())
    return names


def _runtime_import_distributions() -> set[str]:
    """扫描运行时代码并返回直接导入对应的分发包名。

    :return: 返回排除标准库和仓库内模块后的分发包名集合。
    """
    roots = [
        PROJECT_ROOT / "agent_server",
        PROJECT_ROOT / "common",
        PROJECT_ROOT / "loop_optimizer",
        PROJECT_ROOT / "scripts",
        PROJECT_ROOT / "web",
    ]
    imported: set[str] = set()
    for root in roots:
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".", maxsplit=1)[0])
    external = imported - set(sys.stdlib_module_names) - LOCAL_IMPORTS - {"__future__"}
    return {
        re.sub(r"[-_.]+", "-", IMPORT_DISTRIBUTIONS.get(name, name)).lower()
        for name in external
    }


def test_default_model_paths_are_project_relative():
    """验证默认模型目录以项目根目录为基准。

    :return: 无返回值；模型路径偏离项目目录时断言失败。
    """
    from common import constants

    assert constants.BGE_MODEL_PATH == constants.PROJECT_ROOT / "models" / "bge-base-zh-v1.5"
    assert constants.RERANKER_MODEL_PATH == constants.PROJECT_ROOT / "models" / "bge-reranker-base"
    assert constants.VLM_MODEL_DIR == constants.PROJECT_ROOT / "models" / "qwen2.5-vl"


def test_model_paths_can_be_overridden(monkeypatch, tmp_path):
    """验证部署环境可覆盖三个本地模型目录。

    :param monkeypatch: pytest 提供的环境变量替换夹具。
    :param tmp_path: pytest 提供的隔离临时目录。
    :return: 无返回值；路径覆盖未生效时断言失败。
    """
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
    """验证运行模型目录被忽略而公共 Python 包仍受版本控制。

    :return: 无返回值；忽略规则过宽或包文件未追踪时断言失败。
    """
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
    """验证 ECS 模板关闭重组件且不包含真实密钥。

    :return: 无返回值；模板或轻量依赖不符合部署边界时断言失败。
    """
    project_root = Path(__file__).resolve().parents[1]
    text = (project_root / "deploy/knowledge-agent.env.example").read_text(encoding="utf-8")
    requirements = (project_root / "requirements-cloud.txt").read_text(encoding="utf-8").lower()

    assert "VLM_ENABLED=false" in text
    assert "RERANKER_ENABLED=false" in text
    assert "KNOWLEDGE_AGENT_API_BASE_URL=http://127.0.0.1:8000" in text
    assert "QA_LOG_PATH=/opt/knowledge_agent/datas/logs/qa_events.jsonl" in text
    assert "AGNES_API_KEY=" in text
    assert "paddlepaddle" not in requirements
    assert "paddleocr" not in requirements
    assert "bitsandbytes" not in requirements


def test_full_requirements_cover_runtime_imports_and_full_model_stack() -> None:
    """验证本地全量依赖覆盖真实导入及完整模型运行栈。

    :return: 无返回值；任一直接依赖或完整模式必需包缺失时断言失败。
    """
    declared = _requirement_names(PROJECT_ROOT / "requirements.txt")
    expected = _runtime_import_distributions() | {
        "accelerate",
        "bitsandbytes",
        "paddlepaddle",
        "python-multipart",
        "torch",
        "torchvision",
        "uvicorn",
    }

    assert expected - declared == set()


def test_cloud_requirements_keep_lightweight_runtime_contract() -> None:
    """验证轻量依赖仍覆盖云端运行且不显式安装关闭组件。

    :return: 无返回值；云端依赖被削弱或加入重型组件时断言失败。
    """
    declared = _requirement_names(PROJECT_ROOT / "requirements-cloud.txt")
    required = {
        "chromadb",
        "fastapi",
        "httpx",
        "jieba",
        "langchain",
        "langgraph",
        "numpy",
        "openai",
        "pdfplumber",
        "pymupdf",
        "pydantic",
        "python-docx",
        "python-dotenv",
        "python-multipart",
        "rank-bm25",
        "requests",
        "sentence-transformers",
        "streamlit",
        "uvicorn",
    }
    excluded = {"bitsandbytes", "paddleocr", "paddlepaddle"}

    assert required - declared == set()
    assert excluded & declared == set()


def test_systemd_units_use_isolated_directory_and_ports():
    """验证两个 systemd 单元使用隔离目录、账户和端口。

    :return: 无返回值；服务配置与部署约定不一致时断言失败。
    """
    project_root = Path(__file__).resolve().parents[1]
    api = (project_root / "deploy/systemd/knowledge-agent-api.service").read_text(encoding="utf-8")
    web = (project_root / "deploy/systemd/knowledge-agent-web.service").read_text(encoding="utf-8")

    assert "WorkingDirectory=/opt/knowledge_agent" in api
    assert "--host 127.0.0.1 --port 8000" in api
    assert "User=knowledge-agent" in api
    assert "Group=knowledge-agent" in api
    assert "UMask=0027" in api
    assert "WorkingDirectory=/opt/knowledge_agent" in web
    assert "--server.address 0.0.0.0 --server.port 8501" in web
    assert "User=knowledge-agent" in web
    assert "Group=knowledge-agent" in web
    assert "UMask=0027" in web
    assert "Wants=knowledge-agent-api.service" in web


def test_task6_and_readme_define_secure_reproducible_linux_acceptance() -> None:
    """验证正式部署命令统一账户权限、Python 与硬验收边界。

    :return: 无返回值；README 与 Task 6 任一部署契约缺失时断言失败。
    """
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    plan = (
        PROJECT_ROOT / "docs/superpowers/plans/2026-09-03-cloud-lightweight-deployment.md"
    ).read_text(encoding="utf-8")
    required_fragments = {
        "useradd --system",
        "python3.12 -m venv /opt/knowledge_agent/.venv",
        "scripts/bootstrap_admin.py",
        "install -o root -g knowledge-agent -m 640",
        "sudo -u knowledge-agent test -w /opt/knowledge_agent/datas",
        "sudo -u knowledge-agent test -r /opt/knowledge_agent/models/bge-base-zh-v1.5",
        "/opt/knowledge_agent/.venv/bin/python -m pip check",
        "import agent_server.main; import web.app",
        "http://127.0.0.1:8501/_stcore/health",
        "NRestarts",
        "MemoryCurrent",
        "KERNEL_LOG=",
        "grep -Ei 'oom-kill|out of memory|killed process' <<<\"$KERNEL_LOG\" >/dev/null",
        "ss -lntH \"sport = :$PORT\"",
        "set -euo pipefail",
    }

    for document in (readme, plan):
        missing = {fragment for fragment in required_fragments if fragment not in document}
        assert not missing, missing
        assert "python3 -m venv /opt/knowledge_agent/.venv" not in document
    assert "8.154.20.121" not in plan
    assert "KNOWLEDGE_AGENT_ECS_SSH_TARGET" in plan
    assert not re.search(r"pytest 全量 harness：`\d+ passed", readme)


def test_static_checker_rejects_permissive_service_umask(tmp_path: Path) -> None:
    """验证部署检查器拒绝会产生宽松运行文件权限的服务配置。

    :param tmp_path: pytest 提供的隔离临时目录。
    :return: 无返回值；宽松 UMask 未被检查器拒绝时断言失败。
    """
    from scripts.check_deployment_config import validate

    shutil.copytree(PROJECT_ROOT / "deploy", tmp_path / "deploy")
    shutil.copy2(PROJECT_ROOT / "requirements-cloud.txt", tmp_path / "requirements-cloud.txt")
    shutil.copy2(PROJECT_ROOT / "requirements.txt", tmp_path / "requirements.txt")
    api_unit = tmp_path / "deploy/systemd/knowledge-agent-api.service"
    unit_text = api_unit.read_text(encoding="utf-8")
    if "UMask=0027" in unit_text:
        unit_text = unit_text.replace("UMask=0027", "UMask=0022")
    else:
        unit_text = unit_text.replace("Group=knowledge-agent", "Group=knowledge-agent\nUMask=0022")
    api_unit.write_text(unit_text, encoding="utf-8")

    assert "knowledge-agent-api.service [Service]: UMask must be 0027" in validate(tmp_path)


def test_static_checker_rejects_missing_full_runtime_dependency(tmp_path: Path) -> None:
    """验证部署检查器拒绝缺少完整模式直接依赖的 requirements。

    :param tmp_path: pytest 提供的隔离临时目录。
    :return: 无返回值；删除 openai 后检查器未报错时断言失败。
    """
    from scripts.check_deployment_config import validate

    shutil.copytree(PROJECT_ROOT / "deploy", tmp_path / "deploy")
    shutil.copy2(PROJECT_ROOT / "requirements-cloud.txt", tmp_path / "requirements-cloud.txt")
    source_dir = tmp_path / "agent_server/core"
    source_dir.mkdir(parents=True)
    shutil.copy2(PROJECT_ROOT / "agent_server/core/llm_client.py", source_dir / "llm_client.py")
    requirements = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
    without_openai = "\n".join(
        line for line in requirements.splitlines() if line.strip().lower() != "openai"
    )
    (tmp_path / "requirements.txt").write_text(without_openai + "\n", encoding="utf-8")

    assert "requirements.txt missing required dependency: openai" in validate(tmp_path)


def test_static_checker_rejects_missing_cloud_runtime_dependency(tmp_path: Path) -> None:
    """验证部署检查器拒绝被削弱的云端运行依赖集合。

    :param tmp_path: pytest 提供的隔离临时目录。
    :return: 无返回值；删除云端 openai 后检查器未报错时断言失败。
    """
    from scripts.check_deployment_config import validate

    shutil.copytree(PROJECT_ROOT / "deploy", tmp_path / "deploy")
    shutil.copy2(PROJECT_ROOT / "requirements.txt", tmp_path / "requirements.txt")
    requirements = (PROJECT_ROOT / "requirements-cloud.txt").read_text(encoding="utf-8")
    without_openai = "\n".join(
        line for line in requirements.splitlines() if line.strip().lower() != "openai"
    )
    (tmp_path / "requirements-cloud.txt").write_text(without_openai + "\n", encoding="utf-8")

    assert "requirements-cloud.txt missing required dependency: openai" in validate(tmp_path)


def test_static_checker_accepts_committed_deployment_configuration():
    """验证提交的部署配置可通过静态检查器。

    :return: 无返回值；检查器返回非零状态或错误输出时断言失败。
    """
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
    """验证 API 单元禁止绑定公网地址。

    :param tmp_path: pytest 提供的隔离临时目录。
    :return: 无返回值；公网绑定未被检查器拒绝时断言失败。
    """
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
    """验证环境模板拒绝非空 Agnes 密钥。

    :param tmp_path: pytest 提供的隔离临时目录。
    :return: 无返回值；非空密钥未被检查器拒绝时断言失败。
    """
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
    """验证环境模板拒绝冲突的重复键。

    :param tmp_path: pytest 提供的隔离临时目录。
    :return: 无返回值；冲突重复键未被检查器拒绝时断言失败。
    """
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
    """验证被注释的 systemd 指令不能满足部署约束。

    :param tmp_path: pytest 提供的隔离临时目录。
    :return: 无返回值；注释指令被误判为有效时断言失败。
    """
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
    """验证被注释的 dotenv 键不能满足部署约束。

    :param tmp_path: pytest 提供的隔离临时目录。
    :return: 无返回值；注释键被误判为有效时断言失败。
    """
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
