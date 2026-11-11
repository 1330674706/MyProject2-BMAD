"""audit_log 只追加：没有 UPDATE / DELETE（§10.2）。"""

from __future__ import annotations

INSERT_AUDIT = (
    "INSERT INTO audit_log (actor_id, action, target_type, target_id, before_json, after_json, created_at)"
    " VALUES (?, ?, ?, ?, ?, ?, ?)"
)
LIST_RECENT = (
    "SELECT a.id, a.actor_id, a.action, a.target_type, a.target_id,"
    " a.before_json, a.after_json, a.created_at, u.student_no AS actor_student_no"
    " FROM audit_log AS a"
    " LEFT JOIN user AS u ON u.id = a.actor_id"
    " ORDER BY a.created_at DESC, a.id DESC"
    " LIMIT ?"
)
COUNT_ALL = "SELECT COUNT(*) AS total FROM audit_log"


def insert_audit(conn, *, actor_id, action, target_type, target_id, before_json, after_json, created_at) -> None:
    conn.execute(
        INSERT_AUDIT,
        (actor_id, action, target_type, target_id, before_json, after_json, created_at),
    )


def list_recent(conn, limit):
    """按时间倒序读取日志；`student_no` 用于把 actor_id 显示成学号。"""
    return conn.execute(LIST_RECENT, (limit,)).fetchall()


def count_all(conn) -> int:
    return conn.execute(COUNT_ALL).fetchone()["total"]
