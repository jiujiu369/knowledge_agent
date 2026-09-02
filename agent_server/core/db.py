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
                    next_conversation_sequence INTEGER NOT NULL DEFAULT 1,
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
                    ticket_type TEXT NOT NULL DEFAULT 'consultation',
                    leave_type TEXT,
                    start_at TEXT,
                    end_at TEXT,
                    leave_days REAL,
                    leave_reason TEXT,
                    request_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (creator_id) REFERENCES user(id)
                );
                CREATE TABLE IF NOT EXISTS conversation (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    sequence_no INTEGER,
                    request_id TEXT,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES user(id)
                );
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    ticket_id INTEGER,
                    tool_events TEXT NOT NULL DEFAULT '[]',
                    conversation_id INTEGER,
                    request_id TEXT,
                    is_error INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES user(id),
                    FOREIGN KEY (ticket_id) REFERENCES ticket(id),
                    FOREIGN KEY (conversation_id) REFERENCES conversation(id)
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
            if "next_conversation_sequence" not in columns:
                conn.execute("ALTER TABLE user ADD COLUMN next_conversation_sequence INTEGER NOT NULL DEFAULT 1")
            conversation_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(conversation)").fetchall()
            }
            if "sequence_no" not in conversation_columns:
                conn.execute("ALTER TABLE conversation ADD COLUMN sequence_no INTEGER")
            if "request_id" not in conversation_columns:
                conn.execute("ALTER TABLE conversation ADD COLUMN request_id TEXT")
            chat_columns = {row["name"] for row in conn.execute("PRAGMA table_info(chat_history)").fetchall()}
            if "conversation_id" not in chat_columns:
                conn.execute("ALTER TABLE chat_history ADD COLUMN conversation_id INTEGER REFERENCES conversation(id)")
            if "request_id" not in chat_columns:
                conn.execute("ALTER TABLE chat_history ADD COLUMN request_id TEXT")
            if "is_error" not in chat_columns:
                conn.execute("ALTER TABLE chat_history ADD COLUMN is_error INTEGER NOT NULL DEFAULT 0")
            ticket_columns = {row["name"] for row in conn.execute("PRAGMA table_info(ticket)").fetchall()}
            for name, definition in {
                "ticket_type": "TEXT NOT NULL DEFAULT 'consultation'",
                "leave_type": "TEXT",
                "start_at": "TEXT",
                "end_at": "TEXT",
                "leave_days": "REAL",
                "leave_reason": "TEXT",
                "request_id": "TEXT",
            }.items():
                if name not in ticket_columns:
                    conn.execute(f"ALTER TABLE ticket ADD COLUMN {name} {definition}")
            conn.execute("UPDATE ticket SET ticket_type = 'consultation' WHERE ticket_type IS NULL OR ticket_type = ''")
            legacy_users = conn.execute(
                """
                SELECT user_id, MIN(created_at) AS created_at, MAX(created_at) AS updated_at
                FROM chat_history
                WHERE conversation_id IS NULL
                GROUP BY user_id
                """
            ).fetchall()
            for legacy in legacy_users:
                cursor = conn.execute(
                    """
                    INSERT INTO conversation (user_id, title, created_at, updated_at)
                    VALUES (?, '历史对话', ?, ?)
                    """,
                    (legacy["user_id"], legacy["created_at"], legacy["updated_at"]),
                )
                conn.execute(
                    "UPDATE chat_history SET conversation_id = ? WHERE user_id = ? AND conversation_id IS NULL",
                    (cursor.lastrowid, legacy["user_id"]),
                )
            conversation_users = conn.execute("SELECT DISTINCT user_id FROM conversation").fetchall()
            for conversation_user in conversation_users:
                user_id = int(conversation_user["user_id"])
                rows = conn.execute(
                    """
                    SELECT id, sequence_no, title
                    FROM conversation
                    WHERE user_id = ?
                    ORDER BY created_at ASC, id ASC
                    """,
                    (user_id,),
                ).fetchall()
                used = {int(row["sequence_no"]) for row in rows if row["sequence_no"] is not None}
                next_sequence = 1
                for row in rows:
                    sequence_no = row["sequence_no"]
                    if sequence_no is None:
                        while next_sequence in used:
                            next_sequence += 1
                        sequence_no = next_sequence
                        used.add(sequence_no)
                        conn.execute(
                            "UPDATE conversation SET sequence_no = ? WHERE id = ?",
                            (sequence_no, row["id"]),
                        )
                    if row["title"] == f"新对话 {sequence_no}":
                        conn.execute(
                            "UPDATE conversation SET title = ? WHERE id = ?",
                            ("新对话", row["id"]),
                        )
                    next_sequence = max(next_sequence, int(sequence_no) + 1)
                next_sequence = max(used, default=0) + 1
                conn.execute(
                    """
                    UPDATE user
                    SET next_conversation_sequence = MAX(next_conversation_sequence, ?)
                    WHERE id = ?
                    """,
                    (next_sequence, user_id),
                )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conversation_user_updated ON conversation(user_id, updated_at DESC)")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_conversation_user_sequence ON conversation(user_id, sequence_no)"
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_conversation_create_request "
                "ON conversation(user_id, request_id) WHERE request_id IS NOT NULL"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_history_conversation ON chat_history(conversation_id, id DESC)")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_history_request "
                "ON chat_history(user_id, conversation_id, request_id) WHERE request_id IS NOT NULL"
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_ticket_leave_request "
                "ON ticket(creator_id, request_id) WHERE request_id IS NOT NULL"
            )
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
    ticket_type: str = "consultation",
    leave_type: str | None = None,
    start_at: str | None = None,
    end_at: str | None = None,
    leave_days: float | None = None,
    leave_reason: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """创建工单。

    :param title: 函数处理所需的“`title`”数据，类型为 ``str``。
    :param content: 需要处理或写入的文本内容，类型为 ``str``。
    :param creator_id: 函数处理所需的“`creator``id`”数据，类型为 ``int``。
    :param answer: 函数处理所需的“`answer`”数据，类型为 ``str``。
    :param metadata: 函数处理所需的“元数据”数据，类型为 ``str``。
    :param status: 函数处理所需的“获取状态”数据，类型为 ``str``。
    :param ticket_type: 工单类型，只允许普通咨询或请假申请。
    :param leave_type: 请假类别。
    :param start_at: 请假开始时间。
    :param end_at: 请假结束时间。
    :param leave_days: 请假天数。
    :param leave_reason: 请假原因。
    :param request_id: 工单提交幂等标识。
    :return: 返回创建工单得到的结果，返回类型为 ``dict[str, Any]``。
    """
    if ticket_type not in {"consultation", "leave"}:
        raise ValueError("unsupported ticket type")
    timestamp = now_iso()
    with pool().transaction() as conn:
        if request_id is not None:
            existing = conn.execute(
                "SELECT * FROM ticket WHERE creator_id = ? AND request_id = ?",
                (creator_id, request_id),
            ).fetchone()
            if existing:
                return dict(existing)
        cursor = conn.execute(
            """
            INSERT INTO ticket (
                title, content, status, creator_id, answer, metadata, ticket_type,
                leave_type, start_at, end_at, leave_days, leave_reason, request_id,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title, content, status, creator_id, answer, metadata, ticket_type,
                leave_type, start_at, end_at, leave_days, leave_reason, request_id,
                timestamp, timestamp,
            ),
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
        sql = """
            SELECT ticket.*, user.username AS creator_username, user.is_deleted AS creator_is_deleted
            FROM ticket LEFT JOIN user ON user.id = ticket.creator_id
        """
        if include_all:
            rows = conn.execute(sql + " ORDER BY ticket.id DESC").fetchall()
        else:
            rows = conn.execute(
                sql + " WHERE ticket.creator_id = ? ORDER BY ticket.id DESC", (user["id"],)
            ).fetchall()
    return [_public_ticket(row) for row in rows]


def get_ticket(ticket_id: int, user: dict[str, Any], include_all: bool = False) -> dict[str, Any] | None:
    """获取工单。

    :param ticket_id: 函数处理所需的“工单`id`”数据，类型为 ``int``。
    :param user: 函数处理所需的“用户”数据，类型为 ``dict[str, Any]``。
    :param include_all: 函数处理所需的“`include``all`”数据，类型为 ``bool``。
    :return: 返回获取工单得到的结果，返回类型为 ``dict[str, Any] | None``。
    """
    with pool().connection() as conn:
        sql = """
            SELECT ticket.*, user.username AS creator_username, user.is_deleted AS creator_is_deleted
            FROM ticket LEFT JOIN user ON user.id = ticket.creator_id
            WHERE ticket.id = ?
        """
        params: tuple[Any, ...] = (ticket_id,)
        if not include_all:
            sql += " AND ticket.creator_id = ?"
            params = (ticket_id, user["id"])
        row = conn.execute(sql, params).fetchone()
    return _public_ticket(row) if row else None


def _public_ticket(row: sqlite3.Row) -> dict[str, Any]:
    """把工单联表结果转换为不含账户敏感字段的公开结构。

    :param row: 工单与创建人联表查询结果。
    :return: 返回可安全发送给前端的工单字典。
    """
    item = dict(row)
    deleted = bool(item.pop("creator_is_deleted", 0))
    username = str(item.get("creator_username") or "")
    if deleted:
        historical = username.rsplit("__deleted__", 1)[0] or "未知"
        item["creator_username"] = f"账号已删除（原用户名：{historical}）"
    elif not username:
        item["creator_username"] = "账号已删除"
    return item


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


def bulk_approve_pending_consultations() -> dict[str, Any]:
    """在一个事务内批准全部待审批普通咨询工单。

    :return: 返回匹配数量、更新数量和已更新工单编号。
    """
    timestamp = now_iso()
    with pool().transaction() as conn:
        rows = conn.execute(
            "SELECT id FROM ticket WHERE ticket_type = 'consultation' AND status = 'pending' ORDER BY id"
        ).fetchall()
        ticket_ids = [int(row["id"]) for row in rows]
        if ticket_ids:
            placeholders = ",".join("?" for _ in ticket_ids)
            cursor = conn.execute(
                f"UPDATE ticket SET status = 'approved', updated_at = ? "
                f"WHERE ticket_type = 'consultation' AND status = 'pending' AND id IN ({placeholders})",
                (timestamp, *ticket_ids),
            )
            updated_count = cursor.rowcount
        else:
            updated_count = 0
    return {
        "matched_count": len(ticket_ids),
        "updated_count": updated_count,
        "updated_ticket_ids": ticket_ids,
    }


def bulk_process_open_non_leave_tickets() -> dict[str, Any]:
    """在一个事务内将全部待处理非请假工单更新为已处理。

    :return: 返回匹配数量、更新数量和已更新工单编号。
    """
    timestamp = now_iso()
    with pool().transaction() as conn:
        rows = conn.execute(
            "SELECT id FROM ticket WHERE ticket_type != 'leave' AND status = 'open' ORDER BY id"
        ).fetchall()
        ticket_ids = [int(row["id"]) for row in rows]
        if ticket_ids:
            placeholders = ",".join("?" for _ in ticket_ids)
            cursor = conn.execute(
                f"UPDATE ticket SET status = 'processed', updated_at = ? "
                f"WHERE ticket_type != 'leave' AND status = 'open' AND id IN ({placeholders})",
                (timestamp, *ticket_ids),
            )
            updated_count = cursor.rowcount
        else:
            updated_count = 0
    return {
        "matched_count": len(ticket_ids),
        "updated_count": updated_count,
        "updated_ticket_ids": ticket_ids,
    }


def create_conversation(
    user_id: int, title: str = "新对话", request_id: str | None = None
) -> dict[str, Any]:
    """为指定用户创建会话。

    :param user_id: 会话所属用户编号。
    :param title: 会话标题。
    :param request_id: 会话创建请求的幂等标识。
    :return: 返回新建的会话记录。
    """
    timestamp = now_iso()
    with pool().transaction() as conn:
        if request_id is not None:
            existing = conn.execute(
                "SELECT * FROM conversation WHERE user_id = ? AND request_id = ?",
                (user_id, request_id),
            ).fetchone()
            if existing:
                return dict(existing)
        user_row = conn.execute(
            "SELECT next_conversation_sequence FROM user WHERE id = ? AND is_deleted = 0",
            (user_id,),
        ).fetchone()
        if not user_row:
            raise ValueError("user not found")
        sequence_no = int(user_row["next_conversation_sequence"])
        conn.execute(
            "UPDATE user SET next_conversation_sequence = ? WHERE id = ?",
            (sequence_no + 1, user_id),
        )
        stored_title = "新对话" if not title or title.startswith("新对话 ") else title
        cursor = conn.execute(
            """
            INSERT INTO conversation (user_id, sequence_no, request_id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, sequence_no, request_id, stored_title, timestamp, timestamp),
        )
        row = conn.execute("SELECT * FROM conversation WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return dict(row)


def list_conversations(user: dict[str, Any]) -> list[dict[str, Any]]:
    """按创建时间稳定列出当前用户自己的会话。

    :param user: 当前登录用户。
    :return: 返回当前用户的会话列表。
    """
    with pool().connection() as conn:
        rows = conn.execute(
            "SELECT * FROM conversation WHERE user_id = ? ORDER BY created_at ASC, id ASC",
            (user["id"],),
        ).fetchall()
    return [dict(row) for row in rows]


def get_conversation(conversation_id: int, user: dict[str, Any]) -> dict[str, Any] | None:
    """读取当前用户自己的指定会话，不提供管理员越权分支。

    :param conversation_id: 会话编号。
    :param user: 当前登录用户。
    :return: 返回所属会话；不存在或不属于用户时返回空值。
    """
    with pool().connection() as conn:
        row = conn.execute(
            "SELECT * FROM conversation WHERE id = ? AND user_id = ?",
            (conversation_id, user["id"]),
        ).fetchone()
    return row_to_dict(row)


def get_or_create_default_conversation(user_id: int) -> dict[str, Any]:
    """获取兼容旧调用的默认会话，必要时创建。

    :param user_id: 用户编号。
    :return: 返回该用户最早的默认会话。
    """
    with pool().connection() as conn:
        row = conn.execute(
            "SELECT * FROM conversation WHERE user_id = ? ORDER BY id ASC LIMIT 1",
            (user_id,),
        ).fetchone()
    return dict(row) if row else create_conversation(user_id)


def update_conversation_title_from_question(conversation_id: int, user_id: int, question: str) -> None:
    """用第一条问题自动命名仍为默认标题的会话。

    :param conversation_id: 会话编号。
    :param user_id: 会话所属用户编号。
    :param question: 第一条用户问题。
    :return: 无返回值；函数更新会话标题和时间。
    """
    title = question.strip()[:24] or "新对话"
    with pool().transaction() as conn:
        conn.execute(
            """
            UPDATE conversation
            SET title = CASE
                    WHEN title = '新对话' OR title = '新对话 ' || sequence_no THEN ?
                    ELSE title
                END,
                updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (title, now_iso(), conversation_id, user_id),
        )


def delete_conversation(conversation_id: int, user: dict[str, Any]) -> dict[str, Any] | None:
    """删除当前用户自己的会话及其聊天记录，不删除关联工单。

    :param conversation_id: 待删除的会话编号。
    :param user: 当前登录用户。
    :return: 返回被删除的会话；不存在或不属于用户时返回空值。
    """
    with pool().transaction() as conn:
        row = conn.execute(
            "SELECT * FROM conversation WHERE id = ? AND user_id = ?",
            (conversation_id, user["id"]),
        ).fetchone()
        if not row:
            return None
        deleted = dict(row)
        conn.execute(
            "DELETE FROM chat_history WHERE conversation_id = ? AND user_id = ?",
            (conversation_id, user["id"]),
        )
        conn.execute(
            "DELETE FROM conversation WHERE id = ? AND user_id = ?",
            (conversation_id, user["id"]),
        )
        active = conn.execute(
            "SELECT * FROM conversation WHERE user_id = ? ORDER BY updated_at DESC, id DESC LIMIT 1",
            (user["id"],),
        ).fetchone()
        created_replacement = False
        if active is None:
            user_row = conn.execute(
                "SELECT next_conversation_sequence FROM user WHERE id = ? AND is_deleted = 0",
                (user["id"],),
            ).fetchone()
            if not user_row:
                raise ValueError("user not found")
            sequence_no = int(user_row["next_conversation_sequence"])
            conn.execute(
                "UPDATE user SET next_conversation_sequence = ? WHERE id = ?",
                (sequence_no + 1, user["id"]),
            )
            timestamp = now_iso()
            cursor = conn.execute(
                """
                INSERT INTO conversation (user_id, sequence_no, title, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user["id"], sequence_no, "新对话", timestamp, timestamp),
            )
            active = conn.execute(
                "SELECT * FROM conversation WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
            created_replacement = True
    return {
        "deleted": deleted,
        "active_conversation": dict(active),
        "created_replacement": created_replacement,
    }


def create_chat_history(
    user_id: int,
    question: str,
    answer: str,
    ticket_id: int | None = None,
    tool_events: str = "[]",
    conversation_id: int | None = None,
    request_id: str | None = None,
    is_error: bool = False,
) -> dict[str, Any]:
    """创建处理对话历史记录。

    :param user_id: 函数处理所需的“用户`id`”数据，类型为 ``int``。
    :param question: 函数处理所需的“问题”数据，类型为 ``str``。
    :param answer: 函数处理所需的“`answer`”数据，类型为 ``str``。
    :param ticket_id: 函数处理所需的“工单`id`”数据，类型为 ``int | None``。
    :param tool_events: 函数处理所需的“工具`events`”数据，类型为 ``str``。
    :param conversation_id: 消息所属的会话编号。
    :param request_id: 本轮聊天请求的幂等标识。
    :param is_error: 助手内容是否为失败提示。
    :return: 返回创建处理对话历史记录得到的结果，返回类型为 ``dict[str, Any]``。
    """
    created_at = now_iso()
    if conversation_id is None:
        conversation_id = int(get_or_create_default_conversation(user_id)["id"])
    with pool().transaction() as conn:
        owned_conversation = conn.execute(
            "SELECT 1 FROM conversation WHERE id = ? AND user_id = ?",
            (conversation_id, user_id),
        ).fetchone()
        if not owned_conversation:
            raise ValueError("conversation not found")
        if request_id is not None:
            existing = conn.execute(
                """
                SELECT * FROM chat_history
                WHERE user_id = ? AND conversation_id = ? AND request_id = ?
                """,
                (user_id, conversation_id, request_id),
            ).fetchone()
            if existing:
                return dict(existing)
        cursor = conn.execute(
            """
            INSERT INTO chat_history (
                user_id, question, answer, ticket_id, tool_events, conversation_id, request_id, is_error, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id, question, answer, ticket_id, tool_events, conversation_id,
                request_id, int(is_error), created_at,
            ),
        )
        row = conn.execute("SELECT * FROM chat_history WHERE id = ?", (cursor.lastrowid,)).fetchone()
    update_conversation_title_from_question(conversation_id, user_id, question)
    return dict(row)


def list_chat_history(
    user: dict[str, Any], limit: int = 50, conversation_id: int | None = None,
    before_id: int | None = None,
) -> list[dict[str, Any]]:
    """查询列表处理对话历史记录。

    :param user: 函数处理所需的“用户”数据，类型为 ``dict[str, Any]``。
    :param limit: 函数处理所需的“`limit`”数据，类型为 ``int``。
    :param conversation_id: 需要筛选的会话编号。
    :param before_id: 只读取此记录编号之前的数据。
    :return: 返回查询列表处理对话历史记录得到的结果，返回类型为 ``list[dict[str, Any]]``。
    """
    if conversation_id is None:
        conversation_id = int(get_or_create_default_conversation(user["id"])["id"])
    with pool().connection() as conn:
        before_sql = " AND id < ?" if before_id is not None else ""
        params: tuple[Any, ...] = (user["id"], conversation_id)
        if before_id is not None:
            params += (before_id,)
        params += (limit,)
        rows = conn.execute(
            """
            SELECT id, conversation_id, request_id, question, answer, ticket_id, tool_events, is_error, created_at
            FROM chat_history
            WHERE user_id = ? AND conversation_id = ?
            """ + before_sql + """
            ORDER BY id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def delete_chat_history(history_id: int, user: dict[str, Any]) -> dict[str, Any] | None:
    """删除当前用户指定的一整轮问答，并保留会话和关联工单。

    :param history_id: 待删除的聊天记录编号。
    :param user: 当前登录用户。
    :return: 返回已删除记录；记录不存在或不属于当前用户时返回空值。
    """
    with pool().transaction() as conn:
        row = conn.execute(
            """
            SELECT chat_history.* FROM chat_history
            JOIN conversation ON conversation.id = chat_history.conversation_id
            WHERE chat_history.id = ? AND chat_history.user_id = ?
              AND conversation.user_id = ? AND conversation.id = chat_history.conversation_id
            """,
            (history_id, user["id"], user["id"]),
        ).fetchone()
        if not row:
            return None
        deleted = dict(row)
        conn.execute("DELETE FROM chat_history WHERE id = ?", (history_id,))
        remaining = conn.execute(
            "SELECT 1 FROM chat_history WHERE conversation_id = ? LIMIT 1",
            (row["conversation_id"],),
        ).fetchone()
        if remaining is None:
            conn.execute(
                "UPDATE conversation SET title = '新对话', updated_at = ? WHERE id = ? AND user_id = ?",
                (now_iso(), row["conversation_id"], user["id"]),
            )
    return deleted


def list_recent_chat_history(
    user: dict[str, Any], limit: int = 5, conversation_id: int | None = None
) -> list[dict[str, Any]]:
    """查询列表`recent`处理对话历史记录。

    :param user: 函数处理所需的“用户”数据，类型为 ``dict[str, Any]``。
    :param limit: 函数处理所需的“`limit`”数据，类型为 ``int``。
    :param conversation_id: 需要筛选的会话编号。
    :return: 返回查询列表`recent`处理对话历史记录得到的结果，返回类型为 ``list[dict[str, Any]]``。
    """
    if conversation_id is None:
        conversation_id = int(get_or_create_default_conversation(user["id"])["id"])
    with pool().connection() as conn:
        rows = conn.execute(
            """
            SELECT id, conversation_id, request_id, question, answer, ticket_id, tool_events, is_error, created_at
            FROM chat_history
            WHERE user_id = ? AND conversation_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user["id"], conversation_id, limit),
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
