"""occupancy 表仓储；写路径归 booking_service（Story 2.1），本模块不控制事务。"""

from __future__ import annotations

INSERT_OCCUPANCY = (
    "INSERT INTO occupancy (equipment_id, slot_start, kind, booking_id, created_at)"
    " VALUES (?, ?, ?, ?, ?)"
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


def insert_occupancy(conn, equipment_id, slots, booking_id, kind, *, created_at) -> None:
    conn.executemany(
        INSERT_OCCUPANCY,
        [(equipment_id, slot_start, kind, booking_id, created_at) for slot_start in slots],
    )


def select_taken(conn, equipment_id, slots):
    """返回请求中已被占用的行；只用于生成 409 文案，不参与放行或拒绝。"""
    if not slots:
        return []
    placeholders = ", ".join("?" for _ in slots)
    return conn.execute(
        "SELECT equipment_id, slot_start FROM occupancy"
        f" WHERE equipment_id = ? AND slot_start IN ({placeholders})"
        " ORDER BY slot_start",
        (equipment_id, *slots),
    ).fetchall()
