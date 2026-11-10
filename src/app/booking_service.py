"""预约用例：创建（Story 2.1、ADR-001）。写路径归本模块，仓储不控制事务。"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from src.app.slot_rules import (
    CANCEL_LEAD_HOURS,
    CANCEL_STATUS_CANCELLABLE,
    CANCEL_STATUS_PAST_DEADLINE,
    CANCEL_STATUS_STARTED,
    cancel_status,
    validate_cancellable,
    validate_slots,
)
from src.core import redact
from src.core.errors import Conflict, Forbidden, NotFound, Validation
from src.core.ids import new_id
from src.core.timeutil import now_utc, utc_to_local
from src.data import audit_repo, booking_repo, equipment_repo, occupancy_repo
from src.data.tx import write_tx

UNIQUE_SLOT_VIOLATION = "UNIQUE constraint failed: occupancy.equipment_id, occupancy.slot_start"
STATUS_LABELS = {
    CANCEL_STATUS_CANCELLABLE: "可取消",
    CANCEL_STATUS_PAST_DEADLINE: f"已过取消截止（首 slot 前不足 {CANCEL_LEAD_HOURS} 小时）",
    CANCEL_STATUS_STARTED: "已开始",
}


@dataclass(frozen=True)
class MyBooking:
    """“我的预约”只读视图对象；模板只渲染字段，不做归属或时间判断（R1）。"""

    id: str
    equipment_id: str
    equipment_name: str
    slots: tuple[str, ...]
    cancellable: bool
    status_label: str


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


def _slot_display(slot_start: str) -> str:
    return utc_to_local(slot_start).strftime("%m-%d %H:%M")


def list_my_bookings(conn, user_id, now=None):
    """返回当前学生自己的预约只读视图，按创建时间倒序（FR-6）。"""
    now_text = now or now_utc()
    bookings = []
    for row in booking_repo.list_by_owner(conn, user_id):
        slot_rows = occupancy_repo.list_slots_for_booking(conn, row["id"])
        slot_starts = [slot_row["slot_start"] for slot_row in slot_rows]
        status = cancel_status(slot_starts[0], now_text) if slot_starts else CANCEL_STATUS_STARTED
        bookings.append(
            MyBooking(
                id=row["id"],
                equipment_id=row["equipment_id"],
                equipment_name=row["equipment_name"],
                slots=tuple(_slot_display(slot_start) for slot_start in slot_starts),
                cancellable=status == CANCEL_STATUS_CANCELLABLE,
                status_label=STATUS_LABELS[status],
            )
        )
    return bookings


def cancel_booking(conn, user_id, booking_id, now=None):
    """取消整张预约：同一事务删除 booking（级联 occupancy）并写审计（FR-6）。"""
    with write_tx(conn):
        now_text = now or now_utc()
        booking = booking_repo.get_by_id(conn, booking_id)
        if booking is None:
            raise NotFound("预约不存在或已取消")
        if booking["owner_id"] != user_id:
            raise Forbidden("只能取消自己的预约")

        slot_rows = occupancy_repo.list_slots_for_booking(conn, booking_id)
        slot_starts = [row["slot_start"] for row in slot_rows]
        if not slot_starts:
            raise NotFound("预约不存在或已取消")
        validate_cancellable(slot_starts[0], now_text)

        if booking_repo.delete_by_id(conn, booking_id) != 1:
            raise NotFound("预约不存在或已取消")
        audit_repo.insert_audit(
            conn,
            actor_id=user_id,
            action="booking_cancel",
            target_type="booking",
            target_id=booking_id,
            before_json=redact.dump_fields(
                "booking",
                {
                    "id": booking_id,
                    "owner_id": booking["owner_id"],
                    "equipment_id": booking["equipment_id"],
                    "slots": slot_starts,
                    "created_at": booking["created_at"],
                    "updated_at": booking["updated_at"],
                },
            ),
            after_json=None,
            created_at=now_text,
        )
