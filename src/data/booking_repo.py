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
UPDATE_BOOKING = "UPDATE booking SET equipment_id = ?, updated_at = ? WHERE id = ?"
BOOKING_WEEK_COLUMNS = (
    "SELECT b.id AS booking_id, b.owner_id, u.student_no, b.equipment_id,"
    " e.name AS equipment_name, b.created_at, b.updated_at, o.slot_start"
    " FROM booking AS b"
    " JOIN user AS u ON u.id = b.owner_id"
    " JOIN equipment AS e ON e.id = b.equipment_id"
    " JOIN occupancy AS o ON o.booking_id = b.id AND o.kind = 'booking'"
)
LIST_IN_WEEK = (
    BOOKING_WEEK_COLUMNS
    + " WHERE o.slot_start >= ? AND o.slot_start < ?"
    " ORDER BY b.created_at, b.id, o.slot_start"
)
LIST_WEEK_EXPORT = (
    "SELECT e.name AS equipment_name, o.slot_start, u.student_no, b.id AS booking_id"
    " FROM occupancy AS o"
    " JOIN booking AS b ON b.id = o.booking_id"
    " JOIN user AS u ON u.id = b.owner_id"
    " JOIN equipment AS e ON e.id = o.equipment_id"
    " WHERE o.kind = 'booking' AND o.booking_id IS NOT NULL"
    " AND o.slot_start >= ? AND o.slot_start < ?"
    " ORDER BY o.slot_start, e.name, b.id"
)


def insert_booking(conn, *, booking_id, owner_id, equipment_id, created_at, updated_at) -> None:
    conn.execute(INSERT_BOOKING, (booking_id, owner_id, equipment_id, created_at, updated_at))


def get_by_id(conn, booking_id):
    return conn.execute(GET_BY_ID, (booking_id,)).fetchone()


def list_by_owner(conn, owner_id):
    return conn.execute(LIST_BY_OWNER, (owner_id,)).fetchall()


def delete_by_id(conn, booking_id) -> int:
    return conn.execute(DELETE_BY_ID, (booking_id,)).rowcount


def update_booking(conn, *, booking_id, equipment_id, updated_at) -> int:
    return conn.execute(UPDATE_BOOKING, (equipment_id, updated_at, booking_id)).rowcount


def list_in_week(conn, start_utc, end_utc):
    """返回自然周内每条预约占用行，带学生学号与设备名。"""
    return conn.execute(LIST_IN_WEEK, (start_utc, end_utc)).fetchall()


def list_week_export_rows(conn, start_utc, end_utc):
    """返回自然周内可导出的预约占用行：只含 kind='booking'，按 slot 排序。"""
    return conn.execute(LIST_WEEK_EXPORT, (start_utc, end_utc)).fetchall()


def list_for_owners(conn, owner_ids):
    """返回指定学生全部预约占用行，供按学号检索使用。"""
    ids = list(owner_ids)
    if not ids:
        return []
    placeholders = ", ".join("?" for _ in ids)
    return conn.execute(
        BOOKING_WEEK_COLUMNS
        + f" WHERE b.owner_id IN ({placeholders})"
        " ORDER BY b.created_at DESC, b.id, o.slot_start",
        ids,
    ).fetchall()
