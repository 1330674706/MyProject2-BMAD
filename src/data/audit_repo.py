"""audit_log 只追加：没有 UPDATE / DELETE（§10.2）。"""

from __future__ import annotations

INSERT_AUDIT = (
    "INSERT INTO audit_log (actor_id, action, target_type, target_id, before_json, after_json, created_at)"
    " VALUES (?, ?, ?, ?, ?, ?, ?)"
)


def insert_audit(conn, *, actor_id, action, target_type, target_id, before_json, after_json, created_at) -> None:
    conn.execute(
        INSERT_AUDIT,
        (actor_id, action, target_type, target_id, before_json, after_json, created_at),
    )