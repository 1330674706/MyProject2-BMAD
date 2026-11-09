"""user 表仓储；只写参数化 SQL，不控制事务（R2）。"""

from __future__ import annotations

INSERT_USER = (
    "INSERT INTO user (id, student_no, role, password_hash, password_version, active, created_at)"
    " VALUES (?, ?, ?, ?, 1, 1, ?)"
)


def insert_user(conn, *, user_id, student_no, role, password_hash, created_at) -> None:
    conn.execute(INSERT_USER, (user_id, student_no, role, password_hash, created_at))


def get_by_student_no(conn, student_no):
    return conn.execute("SELECT * FROM user WHERE student_no = ?", (student_no,)).fetchone()


def get_by_id(conn, user_id):
    return conn.execute("SELECT * FROM user WHERE id = ?", (user_id,)).fetchone()


def update_password(conn, *, user_id, password_hash) -> int:
    cursor = conn.execute(
        "UPDATE user SET password_hash = ?, password_version = password_version + 1 WHERE id = ?",
        (password_hash, user_id),
    )
    return cursor.rowcount