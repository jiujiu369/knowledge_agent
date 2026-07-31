from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path
from typing import Iterator


def normalize_path(path: str | Path, base_dir: str | Path | None = None) -> Path:
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
    return Path(path).read_text(encoding=encoding)


def safe_write_text(path: str | Path, content: str, encoding: str = "utf-8") -> None:
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
