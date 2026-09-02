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
from tkinter import BOTH, END, LEFT, RIGHT, Button, Entry, Frame, Label, StringVar, Text, Tk, messagebox, simpledialog

from web.frontend_api import localize_error_message


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON_EXE = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
BACKEND_URL = "http://127.0.0.1:8000"
FRONTEND_URL = "http://localhost:8501"
LOG_DIR = PROJECT_ROOT / "docs" / "logs"
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8000
FRONTEND_PORT = 8501


def localize_launcher_error(error: Exception) -> str:
    """将启动器异常转换为安全的中文提示。

    :param error: 启动器捕获的异常。
    :return: 安全中文错误提示。
    """
    return localize_error_message(error)


class ChineseInputDialog(simpledialog.Dialog):
    """使用中文操作按钮的单行输入弹窗。"""

    def __init__(self, parent: Tk, title: str, prompt: str, show: str | None = None) -> None:
        """初始化中文输入弹窗。

        :param parent: 父窗口。
        :param title: 弹窗标题。
        :param prompt: 输入提示。
        :param show: 输入字符替代符。
        :return: 无返回值。
        """
        self.prompt = prompt
        self.show = show
        self.entry: Entry | None = None
        self.result: str | None = None
        super().__init__(parent, title)

    def body(self, master: Frame) -> Entry:
        """创建提示文字和输入框。

        :param master: 弹窗内容容器。
        :return: 需要默认聚焦的输入框。
        """
        Label(master, text=self.prompt, justify=LEFT).grid(row=0, padx=8, pady=(8, 4), sticky="w")
        self.entry = Entry(master, show=self.show or "", width=32)
        self.entry.grid(row=1, padx=8, pady=(0, 8), sticky="ew")
        return self.entry

    def buttonbox(self) -> None:
        """创建中文确定和取消按钮。

        :return: 无返回值。
        """
        box = Frame(self)
        Button(box, text="确定", width=10, command=self.ok, default="active").pack(side=LEFT, padx=5, pady=5)
        Button(box, text="取消", width=10, command=self.cancel).pack(side=LEFT, padx=5, pady=5)
        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)
        box.pack()

    def apply(self) -> None:
        """保存输入结果。

        :return: 无返回值。
        """
        self.result = self.entry.get() if self.entry is not None else ""


def ask_chinese_string(parent: Tk, title: str, prompt: str, show: str | None = None) -> str | None:
    """显示中文单行输入弹窗并返回输入内容。

    :param parent: 父窗口。
    :param title: 弹窗标题。
    :param prompt: 输入提示。
    :param show: 输入字符替代符。
    :return: 用户输入或取消标记。
    """
    return ChineseInputDialog(parent, title, prompt, show).result


def backend_control_states(running: bool, busy: bool = False) -> dict[str, str]:
    """根据后端运行状态返回启动、停止和重启按钮状态。

    :param running: 后端当前是否正在运行。
    :param busy: 后端是否正在执行启动、停止或重启操作。
    :return: 返回三个后端控制按钮对应的 Tkinter 状态。
    """
    if busy:
        return {"start": "disabled", "stop": "disabled", "restart": "disabled"}
    return {
        "start": "disabled" if running else "normal",
        "stop": "normal" if running else "disabled",
        "restart": "normal" if running else "disabled",
    }


def parse_netstat_pids(output: str, port: int) -> set[int]:
    """解析`netstat``pids`。

    :param output: 函数处理所需的“输出”数据，类型为 ``str``。
    :param port: 服务监听或探测使用的 TCP 端口号，类型为 ``int``。
    :return: 返回解析`netstat``pids`得到的结果，返回类型为 ``set[int]``。
    """
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
        """初始化当前对象并保存后续操作所需的状态。

        :return: 无返回值；函数通过副作用、断言或异常完成其职责。
        """
        self.root = Tk()
        self.root.title("企业知识智能助手本地启动器")
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
        """构建界面。

        :return: 无返回值；函数通过副作用、断言或异常完成其职责。
        """
        title = Label(self.root, text="企业知识智能助手本地启动器", font=("Microsoft YaHei UI", 18, "bold"))
        title.pack(anchor="w", padx=18, pady=(16, 8))

        status_frame = Frame(self.root)
        status_frame.pack(fill="x", padx=18, pady=6)
        Label(status_frame, textvariable=self.backend_status, font=("Microsoft YaHei UI", 11)).pack(anchor="w")
        Label(status_frame, textvariable=self.frontend_status, font=("Microsoft YaHei UI", 11)).pack(anchor="w")

        button_frame = Frame(self.root)
        button_frame.pack(fill="x", padx=18, pady=10)

        Button(button_frame, text="检查状态", command=self.check_status, width=18).pack(side=LEFT, padx=(0, 8), pady=4)
        self.start_backend_button = Button(button_frame, text="启动后端", command=self.start_backend, width=18)
        self.start_backend_button.pack(side=LEFT, padx=(0, 8), pady=4)
        self.stop_backend_button = Button(button_frame, text="停止后端", command=self.stop_backend, width=18)
        self.stop_backend_button.pack(side=LEFT, padx=(0, 8), pady=4)
        self.restart_backend_button = Button(button_frame, text="重启后端", command=self.restart_backend, width=18)
        self.restart_backend_button.pack(side=LEFT, padx=(0, 8), pady=4)

        button_frame = Frame(self.root)
        button_frame.pack(fill="x", padx=18, pady=(0, 10))
        second_row_buttons = (
            ("注册管理员", self.register_admin_dialog),
            ("启动前端", self.start_frontend),
            ("打开前端页面", lambda: webbrowser.open(FRONTEND_URL)),
            ("打开后端健康检查", lambda: webbrowser.open(f"{BACKEND_URL}/health")),
        )
        for text, command in second_row_buttons:
            Button(button_frame, text=text, command=command, width=18).pack(side=LEFT, padx=(0, 8), pady=4)

        button_frame = Frame(self.root)
        button_frame.pack(fill="x", padx=18, pady=(0, 10))
        Button(
            button_frame,
            text="停止本窗口启动的服务",
            command=self.stop_started_processes,
            width=18,
        ).pack(side=LEFT, padx=(0, 8), pady=4)

        self._set_backend_controls(running=False)

        url_frame = Frame(self.root)
        url_frame.pack(fill="x", padx=18, pady=(4, 8))
        Label(url_frame, text=f"前端地址：{FRONTEND_URL}", font=("Microsoft YaHei UI", 10)).pack(side=LEFT)
        Label(url_frame, text=f"后端地址：{BACKEND_URL}", font=("Microsoft YaHei UI", 10)).pack(side=RIGHT)

        self.log_box = Text(self.root, height=16, wrap="word", font=("Consolas", 10))
        self.log_box.pack(fill=BOTH, expand=True, padx=18, pady=(4, 16))
        self._log("使用 .venv\\Scripts\\python.exe 启动服务。")

    def _log(self, message: str) -> None:
        """记录。

        :param message: 用户提交或系统生成的消息文本，类型为 ``str``。
        :return: 无返回值；函数通过副作用、断言或异常完成其职责。
        """
        timestamp = time.strftime("%H:%M:%S")
        self.log_box.insert(END, f"[{timestamp}] {message}\n")
        self.log_box.see(END)

    def run(self) -> None:
        """运行。

        :return: 无返回值；函数通过副作用、断言或异常完成其职责。
        """
        self.root.mainloop()

    def check_status(self) -> None:
        """检查获取状态。

        :return: 无返回值；函数通过副作用、断言或异常完成其职责。
        """
        threading.Thread(target=self._check_status_worker, daemon=True).start()

    def _check_status_worker(self) -> None:
        """检查获取状态`worker`。

        :return: 无返回值；函数通过副作用、断言或异常完成其职责。
        """
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
        """设置获取状态。

        :param backend: 函数处理所需的“后端服务”数据，类型为 ``str``。
        :param frontend: 函数处理所需的“前端服务”数据，类型为 ``str``。
        :return: 无返回值；函数通过副作用、断言或异常完成其职责。
        """
        self.backend_status.set(backend)
        self.frontend_status.set(frontend)
        self._set_backend_controls(running=backend == "后端：已运行")
        self._log(f"{backend}；{frontend}")

    def _set_backend_controls(self, running: bool, busy: bool = False) -> None:
        """同步后端控制按钮的可用状态。

        :param running: 后端当前是否正在运行。
        :param busy: 后端是否正在执行控制操作。
        :return: 无返回值；函数直接更新按钮状态。
        """
        states = backend_control_states(running, busy)
        self.start_backend_button.configure(state=states["start"])
        self.stop_backend_button.configure(state=states["stop"])
        self.restart_backend_button.configure(state=states["restart"])

    def _apply_backend_state(self, status: str, running: bool, message: str) -> None:
        """在主线程更新后端状态、按钮和日志。

        :param status: 要显示的后端状态文本。
        :param running: 后端当前是否正在运行。
        :param message: 要写入启动器日志的消息。
        :return: 无返回值；函数直接更新界面。
        """
        self.backend_status.set(status)
        self._set_backend_controls(running=running)
        self._log(message)

    def start_backend(self) -> None:
        """启动后端服务。

        :return: 无返回值；函数通过副作用、断言或异常完成其职责。
        """
        if self._http_ok(f"{BACKEND_URL}/health"):
            self.backend_status.set("后端：已运行")
            self._set_backend_controls(running=True)
            self._log("后端已经在 8000 端口运行。")
            return
        self.backend_status.set("后端：正在启动")
        self._set_backend_controls(running=False, busy=True)
        self._start_backend_process()

    def stop_backend(self) -> None:
        """停止占用 8000 端口的后端服务。

        :return: 无返回值；停止任务在后台线程执行。
        """
        self.backend_status.set("后端：正在停止")
        self._set_backend_controls(running=True, busy=True)
        self._log("正在停止后端。")
        threading.Thread(target=self._stop_backend_worker, daemon=True).start()

    def _stop_backend_worker(self) -> None:
        """在后台停止后端并等待端口释放。

        :return: 无返回值；结果通过主线程更新至界面。
        """
        self._stop_backend()
        for _ in range(20):
            if not self._port_open(BACKEND_HOST, BACKEND_PORT):
                self.root.after(
                    0,
                    lambda: self._apply_backend_state("后端：未运行", False, "后端已停止，8000 端口已释放。"),
                )
                return
            time.sleep(0.5)
        self.root.after(
            0,
            lambda: self._apply_backend_state("后端：停止失败", True, "后端停止失败，8000 端口仍被占用。"),
        )

    def register_admin_dialog(self) -> None:
        """注册管理员`dialog`。

        :return: 无返回值；函数通过副作用、断言或异常完成其职责。
        """
        username = ask_chinese_string(self.root, "注册管理员", "请输入管理员账号：")
        if username is None:
            return
        username = username.strip()
        if not 3 <= len(username) <= 64:
            messagebox.showerror("注册失败", "管理员账号长度必须为 3 到 64 个字符。")
            return

        password = ask_chinese_string(self.root, "注册管理员", "请输入管理员密码（至少 8 位）：", show="*")
        if password is None:
            return
        if not 8 <= len(password) <= 128:
            messagebox.showerror("注册失败", "管理员密码长度必须为 8 到 128 个字符。")
            return

        confirm_password = ask_chinese_string(self.root, "注册管理员", "请再次输入管理员密码：", show="*")
        if confirm_password is None:
            return
        if password != confirm_password:
            messagebox.showerror("注册失败", "两次输入的密码不一致。")
            return

        try:
            user = self._create_local_admin(username, password)
        except Exception as exc:
            messagebox.showerror("注册失败", localize_launcher_error(exc))
            self._log(f"管理员账号注册失败：{username}。")
            return

        self._log(f"已注册管理员账号：{user['username']}。")
        messagebox.showinfo("注册成功", f"管理员账号已创建：{user['username']}")

    @staticmethod
    def _create_local_admin(username: str, password: str) -> dict[str, str]:
        """创建`local`管理员。

        :param username: 用于定位账户的用户名，类型为 ``str``。
        :param password: 函数处理所需的“密码”数据，类型为 ``str``。
        :return: 返回创建`local`管理员得到的结果，返回类型为 ``dict[str, str]``。
        """
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from agent_server.core.auth import register_user

        user = register_user(username=username, password=password, role="admin")
        return {"username": str(user["username"])}

    def restart_backend(self) -> None:
        """重启后端服务。

        :return: 无返回值；函数通过副作用、断言或异常完成其职责。
        """
        threading.Thread(target=self._restart_backend_worker, daemon=True).start()

    def _restart_backend_worker(self) -> None:
        """重启后端服务`worker`。

        :return: 无返回值；函数通过副作用、断言或异常完成其职责。
        """
        self.root.after(0, lambda: self.backend_status.set("后端：正在重启"))
        self.root.after(0, lambda: self._set_backend_controls(running=True, busy=True))
        self.root.after(0, lambda: self._log("正在重启后端。"))
        self._stop_backend()
        for _ in range(20):
            if not self._port_open(BACKEND_HOST, BACKEND_PORT):
                break
            time.sleep(0.5)
        if self._port_open(BACKEND_HOST, BACKEND_PORT):
            self.root.after(
                0,
                lambda: self._apply_backend_state("后端：重启失败", True, "8000 端口仍被占用，未启动新的后端。"),
            )
            return
        self.root.after(0, self._start_backend_process)

    def _start_backend_process(self) -> None:
        """启动后端服务进程。

        :return: 无返回值；函数通过副作用、断言或异常完成其职责。
        """
        if not PYTHON_EXE.exists():
            messagebox.showerror("启动失败", f"找不到虚拟环境：{PYTHON_EXE}")
            self._apply_backend_state("后端：启动失败", False, "找不到项目虚拟环境，后端未启动。")
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
        """停止后端服务。

        :return: 无返回值；函数通过副作用、断言或异常完成其职责。
        """
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
        """后端服务`pids``from`端口。

        :return: 返回后端服务`pids``from`端口得到的结果，返回类型为 ``set[int]``。
        """
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
        """等待`for`后端服务。

        :return: 无返回值；函数通过副作用、断言或异常完成其职责。
        """
        threading.Thread(target=self._wait_for_backend_worker, daemon=True).start()

    def _wait_for_backend_worker(self) -> None:
        """等待`for`后端服务`worker`。

        :return: 无返回值；函数通过副作用、断言或异常完成其职责。
        """
        for _ in range(30):
            if self._http_ok(f"{BACKEND_URL}/health"):
                self.root.after(0, lambda: self._apply_backend_state("后端：已运行", True, "后端启动成功。"))
                return
            time.sleep(1)
        self.root.after(
            0,
            lambda: self._apply_backend_state(
                "后端：启动失败", False, "后端 30 秒内未就绪，请查看 docs\\logs\\backend.log"
            ),
        )

    def start_frontend(self) -> None:
        """启动前端服务。

        :return: 无返回值；函数通过副作用、断言或异常完成其职责。
        """
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
        """等待`for`前端服务。

        :return: 无返回值；函数通过副作用、断言或异常完成其职责。
        """
        threading.Thread(target=self._wait_for_frontend_worker, daemon=True).start()

    def _wait_for_frontend_worker(self) -> None:
        """等待`for`前端服务`worker`。

        :return: 无返回值；函数通过副作用、断言或异常完成其职责。
        """
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
        """停止`started``processes`。

        :return: 无返回值；函数通过副作用、断言或异常完成其职责。
        """
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
        """`on``close`。

        :return: 无返回值；函数通过副作用、断言或异常完成其职责。
        """
        self.root.destroy()

    @staticmethod
    def _http_ok(url: str) -> bool:
        """`http`构造成功响应。

        :param url: 函数处理所需的“`url`”数据，类型为 ``str``。
        :return: 返回`http`构造成功响应得到的结果，返回类型为 ``bool``。
        """
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                return 200 <= response.status < 300
        except (urllib.error.URLError, TimeoutError, OSError):
            return False

    @staticmethod
    def _port_open(host: str, port: int) -> bool:
        """端口打开。

        :param host: 函数处理所需的“`host`”数据，类型为 ``str``。
        :param port: 服务监听或探测使用的 TCP 端口号，类型为 ``int``。
        :return: 返回端口打开得到的结果，返回类型为 ``bool``。
        """
        try:
            with socket.create_connection((host, port), timeout=2):
                return True
        except OSError:
            return False

    @staticmethod
    def _creation_flags() -> int:
        """`creation``flags`。

        :return: 返回`creation``flags`得到的结果，返回类型为 ``int``。
        """
        if os.name != "nt":
            return 0
        return subprocess.CREATE_NO_WINDOW


if __name__ == "__main__":
    if sys.version_info[:2] != (3, 12):
        print("请使用项目 .venv 的 Python 3.12 运行。")
    LocalLauncher().run()
