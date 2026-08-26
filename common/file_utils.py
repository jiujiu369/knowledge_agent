from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path
from typing import Iterator


def normalize_path(path: str | Path, base_dir: str | Path | None = None) -> Path:
    """规范化路径。

    :param path: 目标文件或目录路径，类型为 ``str | Path``。
    :param base_dir: 解析相对路径时使用的基础目录，类型为 ``str | Path | None``。
    :return: 返回规范化路径得到的结果，返回类型为 ``Path``。
    :raises ValueError: 当代码中对应的校验或操作失败条件成立时抛出。
    """
    candidate = Path(path).expanduser()
    if base_dir is not None and not candidate.is_absolute():
        candidate = Path(base_dir) / candidate
    resolved = candidate.resolve()
    if base_dir is not None:
        base = Path(base_dir).expanduser().resolve()
        if resolved != base and base not in resolved.parents:
            raise ValueError(f"Path escapes base directory: {resolved}")
    return resolved


def safe_read_text(path: str | Path, encoding: str = "utf-8") -> str:
    """安全地处理读取文本。

    :param path: 目标文件或目录路径，类型为 ``str | Path``。
    :param encoding: 读取或写入文本时使用的字符编码，类型为 ``str``。
    :return: 返回安全地处理读取文本得到的结果，返回类型为 ``str``。
    """
    return Path(path).read_text(encoding=encoding)


def safe_write_text(path: str | Path, content: str, encoding: str = "utf-8") -> None:
    """安全地处理写入文本。

    :param path: 目标文件或目录路径，类型为 ``str | Path``。
    :param content: 需要处理或写入的文本内容，类型为 ``str``。
    :param encoding: 读取或写入文本时使用的字符编码，类型为 ``str``。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding=encoding,
        dir=target.parent,
        delete=False,
        newline="",
    ) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, target)


@contextlib.contextmanager
def file_lock(lock_path: str | Path) -> Iterator[None]:
    """文件`lock`。

    :param lock_path: 用于协调并发访问的锁文件路径，类型为 ``str | Path``。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    path = Path(lock_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
