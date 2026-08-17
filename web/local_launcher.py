from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, Button, Frame, Label, StringVar, Text, Tk, messagebox, simpledialog


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON_EXE = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
BACKEND_URL = "http://127.0.0.1:8000"
FRONTEND_URL = "http://localhost:8501"
LOG_DIR = PROJECT_ROOT / "docs" / "logs"
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8000
FRONTEND_PORT = 8501


def parse_netstat_pids(output: str, port: int) -> set[int]:
    pids: set[int] = set()
    suffix = f":{port}"
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0].upper() != "TCP":
            continue
        local_address = parts[1]
        state = parts[-2].upper()
        pid_text = parts[-1]
        if state == "LISTENING" and local_address.endswith(suffix) and pid_text.isdigit():
            pids.add(int(pid_text))
    return pids


class LocalLauncher:
    def __init__(self) -> None:
        self.root = Tk()
        self.root.title("Knowledge Agent 本地启动器")
        self.root.geometry("760x520")
        self.root.minsize(680, 460)

        self.backend_process: subprocess.Popen | None = None
        self.frontend_process: subprocess.Popen | None = None
        self.backend_status = StringVar(value="后端：未检测")
        self.frontend_status = StringVar(value="前端：未检测")

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.check_status()

    def _build_ui(self) -> None:
        title = Label(self.root, text="Knowledge Agent 本地启动器", font=("Microsoft YaHei UI", 18, "bold"))
        title.pack(anchor="w", padx=18, pady=(16, 8))

        status_frame = Frame(self.root)
        status_frame.pack(fill="x", padx=18, pady=6)
        Label(status_frame, textvariable=self.backend_status, font=("Microsoft YaHei UI", 11)).pack(anchor="w")
        Label(status_frame, textvariable=self.frontend_status, font=("Microsoft YaHei UI", 11)).pack(anchor="w")

        button_frame = Frame(self.root)
        button_frame.pack(fill="x", padx=18, pady=10)

        buttons = (
            ("检查状态", self.check_status),
            ("启动后端", self.start_backend),
            ("重启后端", self.restart_backend),
            ("注册管理员", self.register_admin_dialog),
            ("启动前端", self.start_frontend),
            ("打开前端页面", lambda: webbrowser.open(FRONTEND_URL)),
            ("打开后端健康检查", lambda: webbrowser.open(f"{BACKEND_URL}/health")),
            ("停止本窗口启动的服务", self.stop_started_processes),
        )
        for index, (text, command) in enumerate(buttons):
            if index == 4:
                button_frame = Frame(self.root)
                button_frame.pack(fill="x", padx=18, pady=(0, 10))
            Button(button_frame, text=text, command=command, width=18).pack(side=LEFT, padx=(0, 8), pady=4)

        url_frame = Frame(self.root)
        url_frame.pack(fill="x", padx=18, pady=(4, 8))
        Label(url_frame, text=f"前端地址：{FRONTEND_URL}", font=("Microsoft YaHei UI", 10)).pack(side=LEFT)
        Label(url_frame, text=f"后端地址：{BACKEND_URL}", font=("Microsoft YaHei UI", 10)).pack(side=RIGHT)

        self.log_box = Text(self.root, height=16, wrap="word", font=("Consolas", 10))
        self.log_box.pack(fill=BOTH, expand=True, padx=18, pady=(4, 16))
        self._log("使用 .venv\\Scripts\\python.exe 启动服务。")

    def _log(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log_box.insert(END, f"[{timestamp}] {message}\n")
        self.log_box.see(END)

    def run(self) -> None:
        self.root.mainloop()

    def check_status(self) -> None:
        threading.Thread(target=self._check_status_worker, daemon=True).start()

    def _check_status_worker(self) -> None:
        backend_ok = self._http_ok(f"{BACKEND_URL}/health")
        frontend_ok = self._port_open(BACKEND_HOST, FRONTEND_PORT)
        self.root.after(
            0,
            lambda: self._set_status(
                "后端：已运行" if backend_ok else "后端：未运行",
                "前端：已运行" if frontend_ok else "前端：未运行",
            ),
        )

    def _set_status(self, backend: str, frontend: str) -> None:
        self.backend_status.set(backend)
        self.frontend_status.set(frontend)
        self._log(f"{backend}；{frontend}")

    def start_backend(self) -> None:
        if self._http_ok(f"{BACKEND_URL}/health"):
            self.backend_status.set("后端：已运行")
            self._log("后端已经在 8000 端口运行。")
            return
        self._start_backend_process()

    def register_admin_dialog(self) -> None:
        username = simpledialog.askstring("注册管理员", "请输入管理员账号：", parent=self.root)
        if username is None:
            return
        username = username.strip()
        if not 3 <= len(username) <= 64:
            messagebox.showerror("注册失败", "管理员账号长度必须为 3 到 64 个字符。")
            return

        password = simpledialog.askstring("注册管理员", "请输入管理员密码（至少 8 位）：", parent=self.root, show="*")
        if password is None:
            return
        if not 8 <= len(password) <= 128:
            messagebox.showerror("注册失败", "管理员密码长度必须为 8 到 128 个字符。")
            return

        confirm_password = simpledialog.askstring("注册管理员", "请再次输入管理员密码：", parent=self.root, show="*")
        if confirm_password is None:
            return
        if password != confirm_password:
            messagebox.showerror("注册失败", "两次输入的密码不一致。")
            return

        try:
            user = self._create_local_admin(username, password)
        except Exception as exc:
            detail = getattr(exc, "detail", None) or str(exc)
            messagebox.showerror("注册失败", f"管理员账号创建失败：{detail}")
            self._log(f"管理员账号注册失败：{username}。")
            return

        self._log(f"已注册管理员账号：{user['username']}。")
        messagebox.showinfo("注册成功", f"管理员账号已创建：{user['username']}")

    @staticmethod
    def _create_local_admin(username: str, password: str) -> dict[str, str]:
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from agent_server.core.auth import register_user

        user = register_user(username=username, password=password, role="admin")
        return {"username": str(user["username"])}

    def restart_backend(self) -> None:
        threading.Thread(target=self._restart_backend_worker, daemon=True).start()

    def _restart_backend_worker(self) -> None:
        self.root.after(0, lambda: self.backend_status.set("后端：正在重启"))
        self.root.after(0, lambda: self._log("正在重启后端。"))
        self._stop_backend()
        for _ in range(20):
            if not self._port_open(BACKEND_HOST, BACKEND_PORT):
                break
            time.sleep(0.5)
        if self._port_open(BACKEND_HOST, BACKEND_PORT):
            self.root.after(0, lambda: self.backend_status.set("后端：重启失败"))
            self.root.after(0, lambda: self._log("8000 端口仍被占用，未启动新的后端。"))
            return
        self.root.after(0, self._start_backend_process)

    def _start_backend_process(self) -> None:
        if not PYTHON_EXE.exists():
            messagebox.showerror("启动失败", f"找不到虚拟环境：{PYTHON_EXE}")
            return

        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = (LOG_DIR / "backend.log").open("a", encoding="utf-8")
        command = [
            str(PYTHON_EXE),
            "-m",
            "uvicorn",
            "agent_server.main:app",
            "--host",
            BACKEND_HOST,
            "--port",
            str(BACKEND_PORT),
        ]
        self.backend_process = subprocess.Popen(
            command,
            cwd=PROJECT_ROOT,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=self._creation_flags(),
        )
        self._log("正在启动后端，日志：docs\\logs\\backend.log")
        self._wait_for_backend()

    def _stop_backend(self) -> None:
        stopped = False
        if self.backend_process and self.backend_process.poll() is None:
            self.backend_process.terminate()
            stopped = True
            self.root.after(0, lambda: self._log("已停止本窗口启动的后端。"))
            try:
                self.backend_process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.backend_process.kill()
                self.root.after(0, lambda: self._log("后端未及时退出，已强制结束。"))
        for pid in self._backend_pids_from_port():
            if pid == os.getpid():
                continue
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                check=False,
                creationflags=self._creation_flags(),
            )
            stopped = True
            if result.returncode == 0:
                self.root.after(0, lambda pid=pid: self._log(f"已停止占用 8000 端口的后端进程 PID={pid}。"))
            else:
                self.root.after(0, lambda pid=pid: self._log(f"停止后端进程 PID={pid} 失败，请手动检查端口。"))
        if not stopped:
            self.root.after(0, lambda: self._log("未发现需要停止的后端进程。"))

    def _backend_pids_from_port(self) -> set[int]:
        if os.name != "nt":
            return set()
        result = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True,
            text=True,
            check=False,
            creationflags=self._creation_flags(),
        )
        if result.returncode != 0:
            return set()
        return parse_netstat_pids(result.stdout, BACKEND_PORT)

    def _wait_for_backend(self) -> None:
        threading.Thread(target=self._wait_for_backend_worker, daemon=True).start()

    def _wait_for_backend_worker(self) -> None:
        for _ in range(30):
            if self._http_ok(f"{BACKEND_URL}/health"):
                self.root.after(0, lambda: self.backend_status.set("后端：已运行"))
                self.root.after(0, lambda: self._log("后端启动成功。"))
                return
            time.sleep(1)
        self.root.after(0, lambda: self.backend_status.set("后端：启动失败"))
        self.root.after(0, lambda: self._log("后端 30 秒内未就绪，请查看 docs\\logs\\backend.log"))

    def start_frontend(self) -> None:
        if self._port_open(BACKEND_HOST, FRONTEND_PORT):
            self.frontend_status.set("前端：已运行")
            self._log("前端已经在 8501 端口运行。")
            webbrowser.open(FRONTEND_URL)
            return
        if not PYTHON_EXE.exists():
            messagebox.showerror("启动失败", f"找不到虚拟环境：{PYTHON_EXE}")
            return

        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = (LOG_DIR / "frontend.log").open("a", encoding="utf-8")
        command = [
            str(PYTHON_EXE),
            "-m",
            "streamlit",
            "run",
            "web/app.py",
            "--server.address",
            "0.0.0.0",
            "--server.port",
            str(FRONTEND_PORT),
            "--browser.gatherUsageStats",
            "false",
        ]
        self.frontend_process = subprocess.Popen(
            command,
            cwd=PROJECT_ROOT,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=self._creation_flags(),
        )
        self._log("正在启动前端，日志：docs\\logs\\frontend.log")
        self._wait_for_frontend()

    def _wait_for_frontend(self) -> None:
        threading.Thread(target=self._wait_for_frontend_worker, daemon=True).start()

    def _wait_for_frontend_worker(self) -> None:
        for _ in range(30):
            if self._port_open(BACKEND_HOST, FRONTEND_PORT):
                self.root.after(0, lambda: self.frontend_status.set("前端：已运行"))
                self.root.after(0, lambda: self._log("前端启动成功，正在打开浏览器。"))
                self.root.after(0, lambda: webbrowser.open(FRONTEND_URL))
                return
            time.sleep(1)
        self.root.after(0, lambda: self.frontend_status.set("前端：启动失败"))
        self.root.after(0, lambda: self._log("前端 30 秒内未就绪，请查看 docs\\logs\\frontend.log"))

    def stop_started_processes(self) -> None:
        stopped = False
        for name, process in (("前端", self.frontend_process),):
            if process and process.poll() is None:
                process.terminate()
                stopped = True
                self._log(f"已停止本窗口启动的{name}。")
        if self.backend_process and self.backend_process.poll() is None:
            self.backend_process.terminate()
            stopped = True
            self._log("已停止本窗口启动的后端。")
        if not stopped:
            self._log("没有发现本窗口启动的运行中服务。")
        self.check_status()

    def _on_close(self) -> None:
        self.root.destroy()

    @staticmethod
    def _http_ok(url: str) -> bool:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                return 200 <= response.status < 300
        except (urllib.error.URLError, TimeoutError, OSError):
            return False

    @staticmethod
    def _port_open(host: str, port: int) -> bool:
        try:
            with socket.create_connection((host, port), timeout=2):
                return True
        except OSError:
            return False

    @staticmethod
    def _creation_flags() -> int:
        if os.name != "nt":
            return 0
        return subprocess.CREATE_NO_WINDOW


if __name__ == "__main__":
    if sys.version_info[:2] != (3, 12):
        print("请使用项目 .venv 的 Python 3.12 运行。")
    LocalLauncher().run()
