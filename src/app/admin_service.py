"""管理员运维视图：本周总览、按学号检索与改单页（FR-3、FR-7）。

六态仍由 `slot_service.build_slot_grid()` 唯一判定；本模块只附加预约归属与异常标记。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta

from src.app import slot_service
from src.core.errors import NotFound, Validation
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


@dataclass(frozen=True)
class BookingEditView:
    booking_id: str
    student_no: str
    equipment_id: str
    equipment_name: str
    week_monday: str
    slots_display: tuple[str, ...]
    grid: object


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


def build_booking_edit_view(
    conn,
    *,
    booking_id,
    viewer_id,
    day=None,
    selected_slots=None,
    conflicted_slots=(),
    conflict_pending=False,
) -> BookingEditView:
    """组装改单页：预约归属、当前时段与按日复用的六态格子。

    `day` 缺省取原预约首个 slot 的本地日期；`selected_slots` 缺省为原时段，
    409 重渲染时传入提交集合——两者只影响展示标记，不参与任何状态判定。
    """
    booking = booking_repo.get_by_id(conn, booking_id)
    if booking is None:
        raise NotFound("预约不存在或已取消")
    rows = occupancy_repo.list_for_booking(conn, booking_id)
    if not rows:
        raise NotFound("预约不存在或已取消")
    equipment = equipment_repo.get_by_id(conn, booking["equipment_id"])
    if equipment is None:
        raise NotFound("设备不存在")

    slots = tuple(row["slot_start"] for row in rows)
    day_text = (day or "").strip() or utc_to_local(slots[0]).date().isoformat()
    selected = slots if selected_slots is None else tuple(selected_slots)
    grid = slot_service.build_slot_grid(
        conn,
        equipment_id=booking["equipment_id"],
        day=day_text,
        viewer_id=viewer_id,
        conflicted_slots=conflicted_slots,
        selected_slots=selected,
        own_slots=slots,
    )
    if not conflicted_slots and not conflict_pending:
        grid = replace(grid, conflict_scope="none")
    owner = user_repo.get_by_id(conn, booking["owner_id"])
    week_monday = week_bounds_utc(utc_to_local(slots[0]).date().isoformat())[0]
    return BookingEditView(
        booking_id=booking_id,
        student_no=owner["student_no"] if owner is not None else "",
        equipment_id=equipment["id"],
        equipment_name=equipment["name"],
        week_monday=week_monday,
        slots_display=tuple(_slot_label(slot_start) for slot_start in slots),
        grid=grid,
    )


def booking_week_monday(conn, booking_id) -> str:
    """返回预约首个 slot 所在的自然周周一，供改单成功后回跳原周视图。"""
    rows = occupancy_repo.list_for_booking(conn, booking_id)
    if not rows:
        raise NotFound("预约不存在或已取消")
    day = utc_to_local(rows[0]["slot_start"]).date().isoformat()
    return week_bounds_utc(day)[0]


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
