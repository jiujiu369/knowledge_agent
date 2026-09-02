from __future__ import annotations

import importlib
import subprocess
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
