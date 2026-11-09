"""equipment 表仓储；只写参数化 SQL，不控制事务（R2）。"""

from __future__ import annotations

INSERT_EQUIPMENT = (
    "INSERT INTO equipment (id, name, open_start, open_end, active)"
    " VALUES (?, ?, ?, ?, 1)"
)
UPDATE_WINDOW = "UPDATE equipment SET name = ?, open_start = ?, open_end = ? WHERE id = ?"


def insert_equipment(conn, *, equipment_id, name, open_start, open_end) -> None:
    conn.execute(INSERT_EQUIPMENT, (equipment_id, name, open_start, open_end))


def list_active(conn):
    return conn.execute("SELECT * FROM equipment WHERE active = 1 ORDER BY name, id").fetchall()


def get_by_id(conn, equipment_id):
    return conn.execute("SELECT * FROM equipment WHERE id = ?", (equipment_id,)).fetchone()


def update_window(conn, *, equipment_id, name, open_start, open_end) -> int:
    cursor = conn.execute(UPDATE_WINDOW, (name, open_start, open_end, equipment_id))
    return cursor.rowcount


def list_occupied_slot_starts(conn, equipment_id, since_utc):
    return conn.execute(
        "SELECT slot_start FROM occupancy"
        " WHERE equipment_id = ? AND slot_start >= ? ORDER BY slot_start",
        (equipment_id, since_utc),
    ).fetchall()
