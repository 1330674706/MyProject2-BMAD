"""预约用例：创建（Story 2.1、ADR-001）。写路径归本模块，仓储不控制事务。"""

from __future__ import annotations

import sqlite3

from src.app.slot_rules import validate_slots
from src.core import redact
from src.core.errors import Conflict, Validation
from src.core.ids import new_id
from src.core.timeutil import now_utc
from src.data import audit_repo, booking_repo, equipment_repo, occupancy_repo
from src.data.tx import write_tx

UNIQUE_SLOT_VIOLATION = "UNIQUE constraint failed: occupancy.equipment_id, occupancy.slot_start"


class _SlotTaken(Exception):
    pass


def _is_slot_clash(error: sqlite3.IntegrityError) -> bool:
    return (
        getattr(error, "sqlite_errorname", "") == "SQLITE_CONSTRAINT_UNIQUE"
        and UNIQUE_SLOT_VIOLATION in str(error)
    )


def _conflict_text(rows) -> str:
    details = "；".join(
        f"equipment_id={row['equipment_id']}, slot_start={row['slot_start']}" for row in rows
    )
    return f"以下 slot 已被占用：{details}"


def create_booking(conn, user_id, equipment_id, slots, now=None):
    booking_id = new_id()
    validated = []
    try:
        with write_tx(conn):
            now_text = now or now_utc()
            equipment = equipment_repo.get_by_id(conn, equipment_id) if equipment_id else None
            if equipment is None or not equipment["active"]:
                raise Validation("设备不存在")
            validated = validate_slots(equipment, slots, now_text)
            booking_repo.insert_booking(
                conn,
                booking_id=booking_id,
                owner_id=user_id,
                equipment_id=equipment_id,
                created_at=now_text,
                updated_at=now_text,
            )
            try:
                occupancy_repo.insert_occupancy(
                    conn,
                    equipment_id,
                    validated,
                    booking_id,
                    "booking",
                    created_at=now_text,
                )
            except sqlite3.IntegrityError as error:
                if _is_slot_clash(error):
                    raise _SlotTaken() from error
                raise Validation("预约写入违反数据库约束") from None
            audit_repo.insert_audit(
                conn,
                actor_id=user_id,
                action="booking_create",
                target_type="booking",
                target_id=booking_id,
                before_json=None,
                after_json=redact.dump_fields(
                    "booking",
                    {
                        "id": booking_id,
                        "owner_id": user_id,
                        "equipment_id": equipment_id,
                        "slots": validated,
                        "created_at": now_text,
                    },
                ),
                created_at=now_text,
            )
    except _SlotTaken:
        conflicts = occupancy_repo.select_taken(conn, equipment_id, validated)
        if not conflicts:
            raise Conflict("所选 slot 已被占用，请刷新后重试") from None
        raise Conflict(
            _conflict_text(conflicts),
            [row["slot_start"] for row in conflicts],
        ) from None
    return booking_id
