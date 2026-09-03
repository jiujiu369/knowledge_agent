from __future__ import annotations

from pathlib import Path


def test_readme_verifier_rejects_default_ubuntu_python_for_ecs(tmp_path: Path, monkeypatch, capsys) -> None:
    """验证 README 检查器拒绝 Ubuntu 默认 Python 创建云端环境。

    :param tmp_path: pytest 提供的隔离临时目录。
    :param monkeypatch: pytest 提供的模块常量替换夹具。
    :param capsys: pytest 提供的标准输出捕获夹具。
    :return: 无返回值；默认 python3 未被拒绝时断言失败。
    """
    from scripts import verify_readme

    source = (verify_readme.PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    candidate = source + "\npython3 -m venv /opt/knowledge_agent/.venv\n"
    readme_path = tmp_path / "README.md"
    readme_path.write_text(candidate, encoding="utf-8")
    monkeypatch.setattr(verify_readme, "README_PATH", readme_path)
    monkeypatch.setattr(verify_readme, "REQUIRED_PATHS", [])

    result = verify_readme.main()

    output = capsys.readouterr().out
    assert result == 1
    assert "Ubuntu ECS commands must use python3.12" in output


def test_readme_verifier_rejects_stale_streamlit_health_endpoint(tmp_path: Path, monkeypatch, capsys) -> None:
    """验证 README 检查器拒绝用前端首页代替健康端点。

    :param tmp_path: pytest 提供的隔离临时目录。
    :param monkeypatch: pytest 提供的模块常量替换夹具。
    :param capsys: pytest 提供的标准输出捕获夹具。
    :return: 无返回值；错误健康检查未被拒绝时断言失败。
    """
    from scripts import verify_readme

    source = (verify_readme.PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    candidate = source + "\ncurl --fail http://127.0.0.1:8501/\n"
    readme_path = tmp_path / "README.md"
    readme_path.write_text(candidate, encoding="utf-8")
    monkeypatch.setattr(verify_readme, "README_PATH", readme_path)
    monkeypatch.setattr(verify_readme, "REQUIRED_PATHS", [])

    result = verify_readme.main()

    output = capsys.readouterr().out
    assert result == 1
    assert "README must use Streamlit /_stcore/health" in output


def test_readme_verifier_rejects_missing_venv_runtime_permissions(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """验证 README 检查器拒绝遗漏服务账户虚拟环境权限收紧步骤。

    :param tmp_path: pytest 提供的隔离临时目录。
    :param monkeypatch: pytest 提供的模块常量替换夹具。
    :param capsys: pytest 提供的标准输出捕获夹具。
    :return: 无返回值；遗漏 ``.venv`` 递归权限命令仍通过时断言失败。
    """
    from scripts import verify_readme

    source = (verify_readme.PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    required = "sudo chown -R root:knowledge-agent /opt/knowledge_agent/.venv\n"
    readme_path = tmp_path / "README.md"
    readme_path.write_text(source.replace(required, ""), encoding="utf-8")
    monkeypatch.setattr(verify_readme, "README_PATH", readme_path)
    monkeypatch.setattr(verify_readme, "REQUIRED_PATHS", [])

    result = verify_readme.main()

    output = capsys.readouterr().out
    assert result == 1
    assert "README missing deployment fragment: chown -R root:knowledge-agent /opt/knowledge_agent/.venv" in output


def test_readme_verifier_rejects_memory_check_before_real_rag_probe(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """验证 README 检查器拒绝空载先测内存的验收顺序。

    :param tmp_path: pytest 提供的隔离临时目录。
    :param monkeypatch: pytest 提供的模块常量替换夹具。
    :param capsys: pytest 提供的标准输出捕获夹具。
    :return: 无返回值；内存检查早于真实 RAG 探针时断言失败。
    """
    from scripts import verify_readme

    source = (verify_readme.PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    correct = "echo 'RAG_LOAD_PHASE=initial'\nrun_real_rag_probe\ncheck_loaded_service_state"
    invalid = "echo 'RAG_LOAD_PHASE=initial'\ncheck_loaded_service_state\nrun_real_rag_probe"
    readme_path = tmp_path / "README.md"
    readme_path.write_text(source.replace(correct, invalid), encoding="utf-8")
    monkeypatch.setattr(verify_readme, "README_PATH", readme_path)
    monkeypatch.setattr(verify_readme, "REQUIRED_PATHS", [])

    result = verify_readme.main()

    output = capsys.readouterr().out
    assert result == 1
    assert "README deployment acceptance order is invalid at: check_loaded_service_state" in output
