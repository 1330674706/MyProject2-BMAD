"""booking 表仓储；只写参数化 SQL，不控制事务（R2）。"""

from __future__ import annotations

INSERT_BOOKING = (
    "INSERT INTO booking (id, owner_id, equipment_id, created_at, updated_at)"
    " VALUES (?, ?, ?, ?, ?)"
)


def insert_booking(conn, *, booking_id, owner_id, equipment_id, created_at, updated_at) -> None:
    conn.execute(INSERT_BOOKING, (booking_id, owner_id, equipment_id, created_at, updated_at))
