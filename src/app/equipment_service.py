"""设备清单与开放时间用例（FR-2、ADR-002、ADR-005）。

业务规则只在这里实现；web/ 只解析表单并交给状态码映射（R1）。
"""

from __future__ import annotations

import re
from datetime import time

from src.core import redact
from src.core.errors import Conflict, NotFound, Validation
from src.core.ids import new_id
from src.core.timeutil import now_utc, utc_to_local
from src.data import audit_repo, equipment_repo
from src.data.tx import write_tx

DEFAULT_OPEN_START = "08:00"
DEFAULT_OPEN_END = "22:00"
WINDOW_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):(?:00|30)$")


def list_equipments(conn):
    return equipment_repo.list_active(conn)


def _parse_window(value: str, label: str) -> tuple[str, time]:
    text = (value or "").strip()
    if not WINDOW_PATTERN.fullmatch(text):
        raise Validation(f"{label}必须是 HH:MM 且对齐 :00 或 :30")
    return text, time.fromisoformat(text)


def _validate_window(open_start: str, open_end: str) -> tuple[str, str]:
    start_text, start_time = _parse_window(open_start, "开放开始时间")
    end_text, end_time = _parse_window(open_end, "开放结束时间")
    if start_time >= end_time:
        raise Validation("开放开始时间必须早于结束时间")
    return start_text, end_text


def create_equipment(conn, *, name, open_start=None, open_end=None, actor_id):
    clean_name = (name or "").strip()
    if not clean_name:
        raise Validation("设备名称不能为空")
    start_text, end_text = _validate_window(
        open_start or DEFAULT_OPEN_START,
        open_end or DEFAULT_OPEN_END,
    )

    equipment_id = new_id()
    with write_tx(conn):
        equipment_repo.insert_equipment(
            conn,
            equipment_id=equipment_id,
            name=clean_name,
            open_start=start_text,
            open_end=end_text,
        )
        audit_repo.insert_audit(
            conn,
            actor_id=actor_id,
            action="equipment_update",
            target_type="equipment",
            target_id=equipment_id,
            before_json=None,
            after_json=redact.dump_fields(
                "equipment",
                {
                    "id": equipment_id,
                    "name": clean_name,
                    "open_start": start_text,
                    "open_end": end_text,
                    "active": 1,
                },
            ),
            created_at=now_utc(),
        )
    return equipment_repo.get_by_id(conn, equipment_id)


def update_window(conn, *, equipment_id, name, open_start, open_end, actor_id):
    start_text, end_text = _validate_window(open_start, open_end)
    start_time = time.fromisoformat(start_text)
    end_time = time.fromisoformat(end_text)

    with write_tx(conn):
        current = equipment_repo.get_by_id(conn, equipment_id)
        if current is None:
            raise NotFound("设备不存在")

        since_utc = now_utc()
        conflicts = [
            row["slot_start"]
            for row in equipment_repo.list_occupied_slot_starts(conn, equipment_id, since_utc)
            if not start_time <= utc_to_local(row["slot_start"]).time() < end_time
        ]
        if conflicts:
            listed = ", ".join(conflicts)
            raise Conflict(f"设备 {equipment_id} 的开放时间与已占用 slot 冲突: {listed}")

        clean_name = (name or "").strip() or current["name"]
        equipment_repo.update_window(
            conn,
            equipment_id=equipment_id,
            name=clean_name,
            open_start=start_text,
            open_end=end_text,
        )
        audit_repo.insert_audit(
            conn,
            actor_id=actor_id,
            action="equipment_update",
            target_type="equipment",
            target_id=equipment_id,
            before_json=redact.dump_fields(
                "equipment",
                {"name": current["name"], "open_start": current["open_start"], "open_end": current["open_end"]},
            ),
            after_json=redact.dump_fields(
                "equipment",
                {"name": clean_name, "open_start": start_text, "open_end": end_text},
            ),
            created_at=now_utc(),
        )
    return equipment_repo.get_by_id(conn, equipment_id)
