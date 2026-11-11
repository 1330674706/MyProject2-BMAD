"""管理员只读运维视图：本周总览与按学号检索（FR-3、FR-7）。

六态仍由 `slot_service.build_slot_grid()` 唯一判定；本模块只附加预约归属与异常标记。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta

from src.app import slot_service
from src.core.errors import Validation
from src.core.timeutil import utc_to_local, week_bounds_utc
from src.data import booking_repo, equipment_repo, occupancy_repo, user_repo

WEEKDAYS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


@dataclass(frozen=True)
class WeekDay:
    date: str
    weekday: str
    grid: object


@dataclass(frozen=True)
class WeekEquipment:
    equipment_id: str
    equipment_name: str
    days: tuple[WeekDay, ...]


@dataclass(frozen=True)
class WeekDayHeader:
    date: str
    weekday: str


@dataclass(frozen=True)
class WeekBooking:
    booking_id: str
    student_no: str
    equipment_id: str
    equipment_name: str
    slots: tuple[str, ...]
    status_label: str


@dataclass(frozen=True)
class WeekView:
    monday: str
    sunday: str
    previous_week: str
    next_week: str
    days: tuple[WeekDayHeader, ...]
    equipments: tuple[WeekEquipment, ...]
    bookings: tuple[WeekBooking, ...]
    anomaly_slots: tuple["AnomalySlot", ...]


@dataclass(frozen=True)
class AnomalySlot:
    slot_start: str
    label: str


@dataclass(frozen=True)
class StudentBooking:
    booking_id: str
    student_no: str
    equipment_id: str
    equipment_name: str
    slots: tuple[str, ...]
    status_label: str


@dataclass(frozen=True)
class StudentSearch:
    query: str
    students: tuple[str, ...]
    bookings: tuple[StudentBooking, ...]
    truncated: bool = False


def _slot_label(slot_start: str) -> str:
    return utc_to_local(slot_start).strftime("%m-%d %H:%M")


def _group_rows(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault(row["booking_id"], []).append(row)
    return grouped


def _overlap_keys(rows):
    seen = {}
    for row in rows:
        key = (row["owner_id"], row["slot_start"])
        seen.setdefault(key, set()).add(row["equipment_id"])
    return {key for key, equipment_ids in seen.items() if len(equipment_ids) > 1}


def _booking_status(edited: bool, overlap: bool) -> str:
    labels = []
    if edited:
        labels.append("已改单")
    if overlap:
        labels.append("跨设备重叠")
    return "、".join(labels) or "正常"


def build_week_view(conn, *, week, viewer_id, now=None) -> WeekView:
    """组装整周只读视图；任何周参数错误都转成 Validation，由 web 层映射 400。"""
    now_text = now or slot_service.now_utc()
    try:
        monday, start_utc, end_utc = week_bounds_utc(week, now=now_text)
    except ValueError:
        raise Validation("周参数必须是 YYYY-MM-DD 或 YYYY-Www") from None

    booking_rows = booking_repo.list_in_week(conn, start_utc, end_utc)
    occupancy_rows = occupancy_repo.list_week_occupancy(conn, start_utc, end_utc)
    booking_index = {(row["equipment_id"], row["slot_start"]): row for row in booking_rows}
    lock_keys = {
        (row["equipment_id"], row["slot_start"])
        for row in occupancy_rows
        if row["kind"] == "lock"
    }
    edited_ids = {
        row["booking_id"]
        for row in booking_rows
        if row["updated_at"] != row["created_at"]
    }
    overlap_keys = _overlap_keys(booking_rows)
    anomaly_slots: dict[tuple[str, str], str] = {}
    shown_slots = set()
    monday_date = date.fromisoformat(monday)

    active_equipments = equipment_repo.list_active(conn)
    equipment_names = {row["id"]: row["name"] for row in active_equipments}
    equipments = []
    for equipment in active_equipments:
        days = []
        for offset in range(7):
            day = (monday_date + timedelta(days=offset)).isoformat()
            grid = slot_service.build_slot_grid(
                conn,
                equipment_id=equipment["id"],
                day=day,
                viewer_id=viewer_id,
                now=now_text,
            )
            cells = []
            for cell in grid.cells:
                shown_slots.add((equipment["id"], cell.start))
                labels = []
                booking = booking_index.get((equipment["id"], cell.start))
                if (equipment["id"], cell.start) in lock_keys:
                    labels.append("已锁定")
                if booking is not None:
                    if booking["booking_id"] in edited_ids:
                        labels.append("已改单")
                    if (booking["owner_id"], cell.start) in overlap_keys:
                        labels.append("跨设备重叠")
                if labels:
                    anomaly_slots[(equipment["id"], cell.start)] = (
                        f"{equipment['name']}（{equipment['id']}）{_slot_label(cell.start)}"
                    )
                cells.append(
                    replace(
                        cell,
                        booking_id=booking["booking_id"] if booking is not None else None,
                        owner_student_no=booking["student_no"] if booking is not None else None,
                        anomaly=bool(labels),
                        anomaly_label="、".join(labels) or None,
                    )
                )
            days.append(
                WeekDay(
                    date=day,
                    weekday=WEEKDAYS[offset],
                    grid=replace(grid, cells=tuple(cells)),
                )
            )
        equipments.append(
            WeekEquipment(
                equipment_id=equipment["id"],
                equipment_name=equipment["name"],
                days=tuple(days),
            )
        )

    for equipment_id, start in lock_keys - shown_slots:
        anomaly_slots[(equipment_id, start)] = (
            f"{equipment_names.get(equipment_id, equipment_id)}（{equipment_id}）"
            f"{_slot_label(start)}（窗口外锁定）"
        )

    bookings = []
    for booking_id, rows in _group_rows(booking_rows).items():
        first = rows[0]
        edited = booking_id in edited_ids
        overlap = any((first["owner_id"], row["slot_start"]) in overlap_keys for row in rows)
        bookings.append(
            WeekBooking(
                booking_id=booking_id,
                student_no=first["student_no"],
                equipment_id=first["equipment_id"],
                equipment_name=first["equipment_name"],
                slots=tuple(_slot_label(row["slot_start"]) for row in rows),
                status_label=_booking_status(edited, overlap),
            )
        )

    return WeekView(
        monday=monday,
        sunday=(monday_date + timedelta(days=6)).isoformat(),
        previous_week=(monday_date - timedelta(days=7)).isoformat(),
        next_week=(monday_date + timedelta(days=7)).isoformat(),
        days=tuple(
            WeekDayHeader(
                date=(monday_date + timedelta(days=offset)).isoformat(),
                weekday=WEEKDAYS[offset],
            )
            for offset in range(7)
        ),
        equipments=tuple(equipments),
        bookings=tuple(bookings),
        anomaly_slots=tuple(
            AnomalySlot(slot_start=start, label=label)
            for (_, start), label in sorted(
                anomaly_slots.items(), key=lambda item: (item[0][1], item[0][0])
            )
        ),
    )


def search_student_bookings(conn, student_no) -> StudentSearch:
    """按学号检索学生及其预约；精确命中优先，查无结果返回空对象。"""
    query = (student_no or "").strip()
    if not query:
        return StudentSearch(query="", students=(), bookings=())

    students, truncated = user_repo.search_by_student_no(conn, query)
    rows = booking_repo.list_for_owners(conn, [student["id"] for student in students])
    overlap_keys = _overlap_keys(rows)
    bookings = []
    for booking_id, group in _group_rows(rows).items():
        first = group[0]
        edited = first["updated_at"] != first["created_at"]
        overlap = any((first["owner_id"], row["slot_start"]) in overlap_keys for row in group)
        bookings.append(
            StudentBooking(
                booking_id=booking_id,
                student_no=first["student_no"],
                equipment_id=first["equipment_id"],
                equipment_name=first["equipment_name"],
                slots=tuple(_slot_label(row["slot_start"]) for row in group),
                status_label=_booking_status(edited, overlap),
            )
        )
    return StudentSearch(
        query=query,
        students=tuple(student["student_no"] for student in students),
        bookings=tuple(bookings),
        truncated=truncated,
    )
