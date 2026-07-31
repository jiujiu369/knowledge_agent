from __future__ import annotations

import argparse
import csv
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


PROJECT_ROOT = Path(__file__).resolve().parent
VENV_PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
RESULTS_DIR = PROJECT_ROOT / "harness_test" / "results"
TMP_DIR = PROJECT_ROOT / "harness_test" / ".tmp"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run M4 pytest, local-service Locust stress, and Allure result export.")
    parser.add_argument("--stress-duration", default="10s", help="Locust run time for each concurrency level.")
    parser.add_argument("--users", nargs="+", type=int, default=[50, 100], help="Concurrency levels.")
    return parser.parse_args()


def ensure_python() -> None:
    if not VENV_PYTHON.exists():
        raise SystemExit(f"missing required Python: {VENV_PYTHON}")
    result = subprocess.run([str(VENV_PYTHON), "--version"], capture_output=True, text=True, check=True)
    version = (result.stdout or result.stderr).strip()
    if version != "Python 3.12.9":
        raise SystemExit(f"required Python 3.12.9, got {version}")


def free_port() -> int:
    for port in range(8010, 8100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("no free local port found in 8010-8099")


def harness_env() -> dict[str, str]:
    env = os.environ.copy()
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    env.update(
        {
            "PYTHONPATH": str(PROJECT_ROOT),
            "DATAS_DIR": str(TMP_DIR / "datas"),
            "CHROMA_DIR": str(TMP_DIR / "chroma"),
            "APP_DB_PATH": str(TMP_DIR / "app.db"),
            "KNOWLEDGE_AGENT_MOCK_LLM": "1",
            "KNOWLEDGE_AGENT_DISABLE_RATE_LIMIT": "1",
            "AGNES_BASE_URL": "https://example.test/v1",
            "AGNES_MODEL": "mock-model",
        }
    )
    env.pop("AGNES_API_KEY", None)
    env.pop("ARK_API_KEY", None)
    return env


def run_command(command: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(command), flush=True)
    return subprocess.run(command, cwd=PROJECT_ROOT, env=env, text=True, capture_output=True, check=False)


def start_server(port: int, env: dict[str, str]) -> subprocess.Popen[str]:
    log_dir = RESULTS_DIR / "server"
    log_dir.mkdir(parents=True, exist_ok=True)
    out = (log_dir / "uvicorn.out.log").open("w", encoding="utf-8")
    err = (log_dir / "uvicorn.err.log").open("w", encoding="utf-8")
    return subprocess.Popen(
        [
            str(VENV_PYTHON),
            "-m",
            "uvicorn",
            "agent_server.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=PROJECT_ROOT,
        env=env,
        stdout=out,
        stderr=err,
        text=True,
    )


def wait_health(port: int, process: subprocess.Popen[str], timeout_seconds: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    url = f"http://127.0.0.1:{port}/health"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"uvicorn exited early with code {process.returncode}")
        try:
            with urlopen(url, timeout=1.0) as response:
                if response.status == 200:
                    return
        except URLError:
            time.sleep(0.3)
    raise RuntimeError("uvicorn health check timed out")


def parse_locust_csv(prefix: Path) -> dict[str, float]:
    stats_path = Path(str(prefix) + "_stats.csv")
    with stats_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    aggregate = next(row for row in rows if row["Name"] == "Aggregated")
    requests = int(float(aggregate["Request Count"]))
    failures = int(float(aggregate["Failure Count"]))
    qps = float(aggregate["Requests/s"])
    p95 = float(aggregate["95%"])
    failure_rate = round((failures / requests * 100.0) if requests else 0.0, 4)
    return {"requests": requests, "failures": failures, "qps": round(qps, 4), "p95_ms": p95, "failure_rate_percent": failure_rate}


def main() -> int:
    args = parse_args()
    ensure_python()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    env = harness_env()

    pytest_result_dir = RESULTS_DIR / "allure"
    pytest_cmd = [
        str(VENV_PYTHON),
        "-m",
        "pytest",
        "harness_test/func",
        "harness_test/edge",
        f"--alluredir={pytest_result_dir}",
        "-q",
    ]
    pytest_result = run_command(pytest_cmd, env)
    print(pytest_result.stdout, end="")
    if pytest_result.returncode != 0:
        print(pytest_result.stderr, file=sys.stderr)
        return pytest_result.returncode

    port = free_port()
    server = start_server(port, env)
    metrics: dict[str, dict[str, float]] = {}
    try:
        wait_health(port, server)
        for users in args.users:
            prefix = RESULTS_DIR / f"locust_{users}"
            locust_cmd = [
                str(VENV_PYTHON),
                "-m",
                "locust",
                "-f",
                "harness_test/stress/locustfile.py",
                "--headless",
                "-u",
                str(users),
                "-r",
                str(users),
                "--run-time",
                args.stress_duration,
                "--host",
                f"http://127.0.0.1:{port}",
                "--csv",
                str(prefix),
                "--only-summary",
                "--exit-code-on-error",
                "1",
            ]
            result = run_command(locust_cmd, env)
            print(result.stdout, end="")
            if result.returncode != 0:
                print(result.stderr, file=sys.stderr)
                return result.returncode
            metrics[str(users)] = parse_locust_csv(prefix)
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()

    summary = {
        "python": "Python 3.12.9",
        "pytest": {"scope": "harness_test/func + harness_test/edge", "status": "passed"},
        "locust": metrics,
        "allure_results": str(pytest_result_dir),
        "isolated_storage": {
            "datas_dir": env["DATAS_DIR"],
            "chroma_dir": env["CHROMA_DIR"],
            "app_db_path": env["APP_DB_PATH"],
        },
    }
    summary_path = RESULTS_DIR / "m4_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
