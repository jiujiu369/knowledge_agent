from __future__ import annotations

import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYTHON_EXE = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"


def test_verify_readme_script_passes():
    result = subprocess.run(
        [str(PYTHON_EXE), "scripts/verify_readme.py"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "README verification passed" in result.stdout
