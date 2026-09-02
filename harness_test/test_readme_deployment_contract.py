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
