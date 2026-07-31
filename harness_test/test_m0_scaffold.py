import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_health_endpoint_returns_ok():
    from agent_server.main import app

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_common_modules_import():
    import common.config_base
    import common.constants
    import common.exception
    import common.file_utils
    import common.logger_base
    import common.models

    assert common.constants.BGE_MODEL_PATH.endswith("models/bge-base-zh-v1.5")


def test_llm_config_defaults_to_agnes_without_key_validation():
    from agent_server.core.config import get_llm_settings

    settings = get_llm_settings(validate_key=False)

    assert settings.base_url == "https://apihub.agnes-ai.com/v1"
    assert settings.model == "agnes-2.0-flash"


def test_main_imports_from_agent_server_workdir():
    result = subprocess.run(
        [sys.executable, "-c", "import main; print(main.app.title)"],
        cwd=PROJECT_ROOT / "agent_server",
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Knowledge Agent" in result.stdout
