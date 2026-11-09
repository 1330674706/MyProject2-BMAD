"""occupancy 表只读查询；写路径归 booking_service（Story 2.1），本模块不控制事务。"""

from __future__ import annotations


def list_for_range(conn, equipment_id, first_slot, last_slot):
    return conn.execute(
        "SELECT o.slot_start, o.kind, b.owner_id"
        " FROM occupancy AS o"
        " LEFT JOIN booking AS b ON b.id = o.booking_id"
        " WHERE o.equipment_id = ? AND o.slot_start >= ? AND o.slot_start <= ?"
        " ORDER BY o.slot_start",
        (equipment_id, first_slot, last_slot),
    ).fetchall()
