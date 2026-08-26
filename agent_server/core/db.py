from __future__ import annotations

import os
import queue
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from common.constants import SQLITE_DB_PATH


_POOL: "SQLitePool | None" = None
_POOL_LOCK = threading.Lock()


def db_path() -> Path:
    """数据库路径。

    :return: 返回数据库路径得到的结果，返回类型为 ``Path``。
    """
    return Path(os.getenv("APP_DB_PATH", str(SQLITE_DB_PATH)))


class SQLitePool:
    def __init__(self, path: Path, size: int = 4) -> None:
        """初始化当前对象并保存后续操作所需的状态。

        :param path: 目标文件或目录路径，类型为 ``Path``。
        :param size: 函数处理所需的“`size`”数据，类型为 ``int``。
        :return: 无返回值；函数通过副作用、断言或异常完成其职责。
        """
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._pool: "queue.Queue[sqlite3.Connection]" = queue.Queue(maxsize=size)
        for _ in range(size):
            self._pool.put(self._connect())
        self.init_schema()

    def _connect(self) -> sqlite3.Connection:
        """`connect`。

        :return: 返回`connect`得到的结果，返回类型为 ``sqlite3.Connection``。
        """
        conn = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """数据库连接。

        :return: 无返回值；函数通过副作用、断言或异常完成其职责。
        """
        conn = self._pool.get()
        try:
            yield conn
        finally:
            self._pool.put(conn)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """`transaction`。

        :return: 无返回值；函数通过副作用、断言或异常完成其职责。
        """
        with self.connection() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def init_schema(self) -> None:
        """初始化数据结构。

        :return: 无返回值；函数通过副作用、断言或异常完成其职责。
        """
        with self.connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS user (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'employee',
                    token TEXT UNIQUE,
                    is_deleted INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ticket (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    creator_id INTEGER NOT NULL,
                    answer TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (creator_id) REFERENCES user(id)
                );
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    ticket_id INTEGER,
                    tool_events TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES user(id),
                    FOREIGN KEY (ticket_id) REFERENCES ticket(id)
                );
                CREATE TABLE IF NOT EXISTS doc (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_path TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    checksum TEXT,
                    chunk_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(user)").fetchall()}
            if "is_deleted" not in columns:
                conn.execute("ALTER TABLE user ADD COLUMN is_deleted INTEGER NOT NULL DEFAULT 0")
            conn.commit()


def pool() -> SQLitePool:
    """`pool`。

    :return: 返回`pool`得到的结果，返回类型为 ``SQLitePool``。
    """
    global _POOL
    path = db_path()
    with _POOL_LOCK:
        if _POOL is None or _POOL.path != path:
            _POOL = SQLitePool(path)
        return _POOL


def reset_db_for_tests() -> None:
    """重置数据库`for``tests`。

    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    global _POOL
    with _POOL_LOCK:
        _POOL = None
    path = db_path()
    for candidate in (path, Path(str(path) + "-wal"), Path(str(path) + "-shm")):
        candidate.unlink(missing_ok=True)


def now_iso() -> str:
    """`now``iso`。

    :return: 返回`now``iso`得到的结果，返回类型为 ``str``。
    """
    return datetime.utcnow().isoformat(timespec="seconds")


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    """`row``to``dict`。

    :param row: 函数处理所需的“`row`”数据，类型为 ``sqlite3.Row | None``。
    :return: 返回`row``to``dict`得到的结果，返回类型为 ``dict[str, Any] | None``。
    """
    return dict(row) if row is not None else None


def create_user(username: str, password_hash: str, role: str) -> dict[str, Any]:
    """创建用户。

    :param username: 用于定位账户的用户名，类型为 ``str``。
    :param password_hash: 函数处理所需的“密码计算哈希”数据，类型为 ``str``。
    :param role: 用于权限判断的用户角色标识，类型为 ``str``。
    :return: 返回创建用户得到的结果，返回类型为 ``dict[str, Any]``。
    """
    created_at = now_iso()
    with pool().transaction() as conn:
        cursor = conn.execute(
            "INSERT INTO user (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            (username, password_hash, role, created_at),
        )
        row = conn.execute("SELECT * FROM user WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return dict(row)


def get_user_by_username(username: str) -> dict[str, Any] | None:
    """获取用户`by`用户名。

    :param username: 用于定位账户的用户名，类型为 ``str``。
    :return: 返回获取用户`by`用户名得到的结果，返回类型为 ``dict[str, Any] | None``。
    """
    with pool().connection() as conn:
        return row_to_dict(conn.execute("SELECT * FROM user WHERE username = ? AND is_deleted = 0", (username,)).fetchone())


def get_user_by_token(token: str) -> dict[str, Any] | None:
    """获取用户`by`令牌。

    :param token: 用于身份认证或模型处理的令牌值，类型为 ``str``。
    :return: 返回获取用户`by`令牌得到的结果，返回类型为 ``dict[str, Any] | None``。
    """
    with pool().connection() as conn:
        return row_to_dict(conn.execute("SELECT * FROM user WHERE token = ? AND is_deleted = 0", (token,)).fetchone())


def set_user_token(user_id: int, token: str) -> None:
    """设置用户令牌。

    :param user_id: 函数处理所需的“用户`id`”数据，类型为 ``int``。
    :param token: 用于身份认证或模型处理的令牌值，类型为 ``str``。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    with pool().transaction() as conn:
        conn.execute("UPDATE user SET token = ? WHERE id = ?", (token, user_id))


def update_user_password(user_id: int, password_hash: str) -> bool:
    """更新用户密码。

    :param user_id: 函数处理所需的“用户`id`”数据，类型为 ``int``。
    :param password_hash: 函数处理所需的“密码计算哈希”数据，类型为 ``str``。
    :return: 返回更新用户密码得到的结果，返回类型为 ``bool``。
    """
    with pool().transaction() as conn:
        cursor = conn.execute(
            "UPDATE user SET password_hash = ?, token = NULL WHERE id = ? AND is_deleted = 0",
            (password_hash, user_id),
        )
    return cursor.rowcount > 0


def delete_user(user_id: int) -> bool:
    """删除用户。

    :param user_id: 函数处理所需的“用户`id`”数据，类型为 ``int``。
    :return: 返回删除用户得到的结果，返回类型为 ``bool``。
    """
    with pool().transaction() as conn:
        cursor = conn.execute(
            """
            UPDATE user
            SET username = username || '__deleted__' || id,
                is_deleted = 1,
                token = NULL
            WHERE id = ? AND is_deleted = 0
            """,
            (user_id,),
        )
    return cursor.rowcount > 0


def list_users() -> list[dict[str, Any]]:
    """查询列表`users`。

    :return: 返回查询列表`users`得到的结果，返回类型为 ``list[dict[str, Any]]``。
    """
    with pool().connection() as conn:
        rows = conn.execute(
            "SELECT id, username, role, created_at FROM user WHERE is_deleted = 0 ORDER BY id DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def create_ticket(
    title: str,
    content: str,
    creator_id: int,
    answer: str = "",
    metadata: str = "{}",
    status: str = "pending",
) -> dict[str, Any]:
    """创建工单。

    :param title: 函数处理所需的“`title`”数据，类型为 ``str``。
    :param content: 需要处理或写入的文本内容，类型为 ``str``。
    :param creator_id: 函数处理所需的“`creator``id`”数据，类型为 ``int``。
    :param answer: 函数处理所需的“`answer`”数据，类型为 ``str``。
    :param metadata: 函数处理所需的“元数据”数据，类型为 ``str``。
    :param status: 函数处理所需的“获取状态”数据，类型为 ``str``。
    :return: 返回创建工单得到的结果，返回类型为 ``dict[str, Any]``。
    """
    timestamp = now_iso()
    with pool().transaction() as conn:
        cursor = conn.execute(
            """
            INSERT INTO ticket (title, content, status, creator_id, answer, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (title, content, status, creator_id, answer, metadata, timestamp, timestamp),
        )
        row = conn.execute("SELECT * FROM ticket WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return dict(row)


def list_tickets(user: dict[str, Any], include_all: bool = False) -> list[dict[str, Any]]:
    """查询列表`tickets`。

    :param user: 函数处理所需的“用户”数据，类型为 ``dict[str, Any]``。
    :param include_all: 函数处理所需的“`include``all`”数据，类型为 ``bool``。
    :return: 返回查询列表`tickets`得到的结果，返回类型为 ``list[dict[str, Any]]``。
    """
    with pool().connection() as conn:
        if include_all:
            rows = conn.execute("SELECT * FROM ticket ORDER BY id DESC").fetchall()
        else:
            rows = conn.execute("SELECT * FROM ticket WHERE creator_id = ? ORDER BY id DESC", (user["id"],)).fetchall()
    return [dict(row) for row in rows]


def get_ticket(ticket_id: int, user: dict[str, Any], include_all: bool = False) -> dict[str, Any] | None:
    """获取工单。

    :param ticket_id: 函数处理所需的“工单`id`”数据，类型为 ``int``。
    :param user: 函数处理所需的“用户”数据，类型为 ``dict[str, Any]``。
    :param include_all: 函数处理所需的“`include``all`”数据，类型为 ``bool``。
    :return: 返回获取工单得到的结果，返回类型为 ``dict[str, Any] | None``。
    """
    with pool().connection() as conn:
        if include_all:
            row = conn.execute("SELECT * FROM ticket WHERE id = ?", (ticket_id,)).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM ticket WHERE id = ? AND creator_id = ?",
                (ticket_id, user["id"]),
            ).fetchone()
    return row_to_dict(row)


def update_ticket_status(ticket_id: int, status: str, user: dict[str, Any], include_all: bool = False) -> dict[str, Any] | None:
    """更新工单获取状态。

    :param ticket_id: 函数处理所需的“工单`id`”数据，类型为 ``int``。
    :param status: 函数处理所需的“获取状态”数据，类型为 ``str``。
    :param user: 函数处理所需的“用户”数据，类型为 ``dict[str, Any]``。
    :param include_all: 函数处理所需的“`include``all`”数据，类型为 ``bool``。
    :return: 返回更新工单获取状态得到的结果，返回类型为 ``dict[str, Any] | None``。
    """
    timestamp = now_iso()
    with pool().transaction() as conn:
        if include_all:
            cursor = conn.execute("UPDATE ticket SET status = ?, updated_at = ? WHERE id = ?", (status, timestamp, ticket_id))
        else:
            cursor = conn.execute(
                "UPDATE ticket SET status = ?, updated_at = ? WHERE id = ? AND creator_id = ?",
                (status, timestamp, ticket_id, user["id"]),
            )
        if cursor.rowcount == 0:
            return None
        row = conn.execute("SELECT * FROM ticket WHERE id = ?", (ticket_id,)).fetchone()
    return row_to_dict(row)


def ticket_stats() -> dict[str, Any]:
    """工单`stats`。

    :return: 返回工单`stats`得到的结果，返回类型为 ``dict[str, Any]``。
    """
    with pool().connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM ticket").fetchone()[0]
        rows = conn.execute("SELECT status, COUNT(*) AS count FROM ticket GROUP BY status").fetchall()
    return {"total": total, "by_status": {row["status"]: row["count"] for row in rows}}


def create_chat_history(
    user_id: int,
    question: str,
    answer: str,
    ticket_id: int | None = None,
    tool_events: str = "[]",
) -> dict[str, Any]:
    """创建处理对话历史记录。

    :param user_id: 函数处理所需的“用户`id`”数据，类型为 ``int``。
    :param question: 函数处理所需的“问题”数据，类型为 ``str``。
    :param answer: 函数处理所需的“`answer`”数据，类型为 ``str``。
    :param ticket_id: 函数处理所需的“工单`id`”数据，类型为 ``int | None``。
    :param tool_events: 函数处理所需的“工具`events`”数据，类型为 ``str``。
    :return: 返回创建处理对话历史记录得到的结果，返回类型为 ``dict[str, Any]``。
    """
    created_at = now_iso()
    with pool().transaction() as conn:
        cursor = conn.execute(
            """
            INSERT INTO chat_history (user_id, question, answer, ticket_id, tool_events, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, question, answer, ticket_id, tool_events, created_at),
        )
        row = conn.execute("SELECT * FROM chat_history WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return dict(row)


def list_chat_history(user: dict[str, Any], limit: int = 50) -> list[dict[str, Any]]:
    """查询列表处理对话历史记录。

    :param user: 函数处理所需的“用户”数据，类型为 ``dict[str, Any]``。
    :param limit: 函数处理所需的“`limit`”数据，类型为 ``int``。
    :return: 返回查询列表处理对话历史记录得到的结果，返回类型为 ``list[dict[str, Any]]``。
    """
    with pool().connection() as conn:
        rows = conn.execute(
            """
            SELECT id, question, answer, ticket_id, tool_events, created_at
            FROM chat_history
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user["id"], limit),
        ).fetchall()
    return [dict(row) for row in rows]


def list_recent_chat_history(user: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    """查询列表`recent`处理对话历史记录。

    :param user: 函数处理所需的“用户”数据，类型为 ``dict[str, Any]``。
    :param limit: 函数处理所需的“`limit`”数据，类型为 ``int``。
    :return: 返回查询列表`recent`处理对话历史记录得到的结果，返回类型为 ``list[dict[str, Any]]``。
    """
    with pool().connection() as conn:
        rows = conn.execute(
            """
            SELECT id, question, answer, ticket_id, tool_events, created_at
            FROM chat_history
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user["id"], limit),
        ).fetchall()
    return [dict(row) for row in reversed(rows)]


def upsert_doc(source_path: str, title: str, checksum: str | None = None, chunk_count: int = 0) -> dict[str, Any]:
    """新增或更新知识文档。

    :param source_path: 函数处理所需的“源文件路径”数据，类型为 ``str``。
    :param title: 函数处理所需的“`title`”数据，类型为 ``str``。
    :param checksum: 函数处理所需的“`checksum`”数据，类型为 ``str | None``。
    :param chunk_count: 函数处理所需的“切分`count`”数据，类型为 ``int``。
    :return: 返回新增或更新知识文档得到的结果，返回类型为 ``dict[str, Any]``。
    """
    timestamp = now_iso()
    with pool().transaction() as conn:
        conn.execute(
            """
            INSERT INTO doc (source_path, title, checksum, chunk_count, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_path) DO UPDATE SET
                title=excluded.title,
                checksum=excluded.checksum,
                chunk_count=excluded.chunk_count,
                updated_at=excluded.updated_at
            """,
            (source_path, title, checksum, chunk_count, timestamp, timestamp),
        )
        row = conn.execute("SELECT * FROM doc WHERE source_path = ?", (source_path,)).fetchone()
    return dict(row)


def list_docs() -> list[dict[str, Any]]:
    """查询列表`docs`。

    :return: 返回查询列表`docs`得到的结果，返回类型为 ``list[dict[str, Any]]``。
    """
    with pool().connection() as conn:
        rows = conn.execute("SELECT * FROM doc ORDER BY id DESC").fetchall()
    return [dict(row) for row in rows]


def get_doc(doc_id: int) -> dict[str, Any] | None:
    """获取知识文档。

    :param doc_id: 函数处理所需的“知识文档`id`”数据，类型为 ``int``。
    :return: 返回获取知识文档得到的结果，返回类型为 ``dict[str, Any] | None``。
    """
    with pool().connection() as conn:
        row = conn.execute("SELECT * FROM doc WHERE id = ?", (doc_id,)).fetchone()
    return row_to_dict(row)


def delete_doc(doc_id: int) -> dict[str, Any] | None:
    """删除知识文档。

    :param doc_id: 函数处理所需的“知识文档`id`”数据，类型为 ``int``。
    :return: 返回删除知识文档得到的结果，返回类型为 ``dict[str, Any] | None``。
    """
    timestamp = now_iso()
    with pool().transaction() as conn:
        row = conn.execute("SELECT * FROM doc WHERE id = ?", (doc_id,)).fetchone()
        if row is None:
            return None
        conn.execute("DELETE FROM doc WHERE id = ?", (doc_id,))
    deleted = dict(row)
    deleted["deleted_at"] = timestamp
    return deleted
