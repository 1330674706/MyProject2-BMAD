"""occupancy 表仓储；写路径归 booking_service（Story 2.1），本模块不控制事务。"""

from __future__ import annotations

INSERT_OCCUPANCY = (
    "INSERT INTO occupancy (equipment_id, slot_start, kind, booking_id, created_at)"
    " VALUES (?, ?, ?, ?, ?)"
)
DELETE_FOR_BOOKING = "DELETE FROM occupancy WHERE booking_id = ? AND kind = 'booking'"
DELETE_LOCKS = (
    "DELETE FROM occupancy WHERE equipment_id = ? AND kind = 'lock'"
    " AND slot_start IN ({placeholders})"
)
LIST_FOR_BOOKING = (
    "SELECT equipment_id, slot_start, kind, booking_id FROM occupancy"
    " WHERE booking_id = ? ORDER BY slot_start"
)
LIST_WEEK_OCCUPANCY = (
    "SELECT o.equipment_id, o.slot_start, o.kind, o.booking_id, b.owner_id"
    " FROM occupancy AS o"
    " LEFT JOIN booking AS b ON b.id = o.booking_id"
    " WHERE o.slot_start >= ? AND o.slot_start < ?"
    " ORDER BY o.slot_start, o.equipment_id"
)


def list_for_range(conn, equipment_id, first_slot, last_slot):
    return conn.execute(
        "SELECT o.slot_start, o.kind, b.owner_id"
        " FROM occupancy AS o"
        " LEFT JOIN booking AS b ON b.id = o.booking_id"
        " WHERE o.equipment_id = ? AND o.slot_start >= ? AND o.slot_start <= ?"
        " ORDER BY o.slot_start",
        (equipment_id, first_slot, last_slot),
    ).fetchall()


def list_week_occupancy(conn, start_utc, end_utc):
    """按自然周半开区间读取占用行，供管理员周视图附加归属与异常。"""
    return conn.execute(LIST_WEEK_OCCUPANCY, (start_utc, end_utc)).fetchall()


def insert_occupancy(conn, equipment_id, slots, booking_id, kind, *, created_at) -> None:
    conn.executemany(
        INSERT_OCCUPANCY,
        [(equipment_id, slot_start, kind, booking_id, created_at) for slot_start in slots],
    )


def list_slots_for_booking(conn, booking_id):
    """按 slot_start 升序返回该预约的全部占用行。"""
    return conn.execute(
        "SELECT slot_start FROM occupancy WHERE booking_id = ? ORDER BY slot_start",
        (booking_id,),
    ).fetchall()


def list_for_booking(conn, booking_id):
    """返回该预约的完整占用行，供改单前快照与审计使用。"""
    return conn.execute(LIST_FOR_BOOKING, (booking_id,)).fetchall()


def delete_occupancy(conn, booking_id) -> int:
    """删除该预约的 booking 占用行；锁定行 booking_id 为 NULL，不受影响。"""
    return conn.execute(DELETE_FOR_BOOKING, (booking_id,)).rowcount


def delete_lock_rows(conn, equipment_id, slots) -> int:
    """只删锁定行；rowcount 供用例判断"无锁可解"是否 404。"""
    if not slots:
        return 0
    placeholders = ", ".join("?" for _ in slots)
    return conn.execute(
        DELETE_LOCKS.format(placeholders=placeholders),
        (equipment_id, *slots),
    ).rowcount


def select_taken(conn, equipment_id, slots, exclude_booking_id=None):
    """返回请求中已被占用的行；只用于生成 409 文案，不参与放行或拒绝。"""
    if not slots:
        return []
    placeholders = ", ".join("?" for _ in slots)
    params = [equipment_id, *slots]
    exclusion = ""
    if exclude_booking_id is not None:
        exclusion = " AND (booking_id IS NULL OR booking_id <> ?)"
        params.append(exclude_booking_id)
    return conn.execute(
        "SELECT equipment_id, slot_start FROM occupancy"
        f" WHERE equipment_id = ? AND slot_start IN ({placeholders})"
        f"{exclusion}"
        " ORDER BY slot_start",
        params,
    ).fetchall()
