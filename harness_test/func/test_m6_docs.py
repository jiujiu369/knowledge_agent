from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_verify_readme_script_passes():
    """验证验证README 文档`script``passes`。

    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    result = subprocess.run(
        [sys.executable, "scripts/verify_readme.py"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "README verification passed" in result.stdout
