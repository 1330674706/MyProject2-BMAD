"""booking 表仓储；只写参数化 SQL，不控制事务（R2）。"""

from __future__ import annotations

INSERT_BOOKING = (
    "INSERT INTO booking (id, owner_id, equipment_id, created_at, updated_at)"
    " VALUES (?, ?, ?, ?, ?)"
)
GET_BY_ID = (
    "SELECT id, owner_id, equipment_id, created_at, updated_at FROM booking WHERE id = ?"
)
LIST_BY_OWNER = (
    "SELECT b.id, b.owner_id, b.equipment_id, b.created_at, b.updated_at,"
    " e.name AS equipment_name"
    " FROM booking AS b JOIN equipment AS e ON e.id = b.equipment_id"
    " WHERE b.owner_id = ? ORDER BY b.created_at DESC, b.id"
)
DELETE_BY_ID = "DELETE FROM booking WHERE id = ?"


def insert_booking(conn, *, booking_id, owner_id, equipment_id, created_at, updated_at) -> None:
    conn.execute(INSERT_BOOKING, (booking_id, owner_id, equipment_id, created_at, updated_at))


def get_by_id(conn, booking_id):
    return conn.execute(GET_BY_ID, (booking_id,)).fetchone()


def list_by_owner(conn, owner_id):
    return conn.execute(LIST_BY_OWNER, (owner_id,)).fetchall()


def delete_by_id(conn, booking_id) -> int:
    return conn.execute(DELETE_BY_ID, (booking_id,)).rowcount
