"""slot 派生与六态视图：时间形状与占用状态的唯一生产者（FR-2、FR-3、ADR-005）。

slot 是派生量，不建表；`build_grid()` 只负责时间，`build_slot_grid()` 在其上叠加占用状态。
状态枚举是 2.1 与 3.1 的共同契约，只允许六个值。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from src.core.errors import NotFound, Validation
from src.core.timeutil import add_days, local_at, local_to_utc, now_utc, utc_to_local
from src.data import equipment_repo, occupancy_repo

SLOT_MINUTES = 30
WINDOW_DAYS = 7

SIX_STATES = frozenset(
    {
        "free",
        "booked_by_self",
        "booked_by_other",
        "locked",
        "closed_past",
        "closed_window",
    }
)

STATE_LABELS = {
    "free": "空闲",
    "booked_by_self": "我的预约",
    "booked_by_other": "已被占用",
    "locked": "已锁定",
    "closed_past": "已开始",
    "closed_window": "超出可约窗口",
}

CONFLICT_SCOPES = frozenset({"none", "cells", "page"})


@dataclass(frozen=True)
class SlotCell:
    start: str
    local_time: str
    state: str
    conflicted: bool = False
    selected: bool = False

    def __post_init__(self) -> None:
        if self.state not in SIX_STATES:
            raise ValueError(f"未知 slot 状态: {self.state}")

    @property
    def label(self) -> str:
        return STATE_LABELS[self.state]

    @property
    def selectable(self) -> bool:
        return self.state == "free"


@dataclass(frozen=True)
class SlotGrid:
    equipment_id: str
    day: str
    open_start: str
    open_end: str
    cells: tuple[SlotCell, ...]
    conflict_scope: str = "none"

    def __post_init__(self) -> None:
        if self.conflict_scope not in CONFLICT_SCOPES:
            raise ValueError(f"未知冲突作用域: {self.conflict_scope}")

    def __iter__(self):
        return iter(self.cells)

    def __len__(self) -> int:
        return len(self.cells)

    def __getitem__(self, key):
        for cell in self.cells:
            if key in (cell.local_time, cell.start):
                return cell
        raise KeyError(key)


def build_grid(open_start: str, open_end: str, day: str) -> list[str]:
    """按本地开放窗口派生某天的 slot，返回 20 字符 UTC 文本列表。"""
    try:
        cursor = local_at(day, open_start)
        end = local_at(day, open_end)
    except ValueError:
        raise Validation("日期或开放时间格式不正确") from None
    if cursor >= end:
        raise Validation("开放开始时间必须早于结束时间")

    slots: list[str] = []
    step = timedelta(minutes=SLOT_MINUTES)
    while cursor < end:
        slots.append(local_to_utc(cursor))
        cursor += step
    return slots


def _resolve_state(start, now_text, window_end, row, viewer_id) -> str:
    if start <= now_text:
        return "closed_past"
    if start > window_end:
        return "closed_window"
    if row is None:
        return "free"
    if row["kind"] == "lock":
        return "locked"
    if row["owner_id"] == viewer_id:
        return "booked_by_self"
    return "booked_by_other"


def build_slot_grid(
    conn,
    *,
    equipment_id,
    day,
    viewer_id,
    now=None,
    conflicted_slots=(),
    selected_slots=(),
) -> SlotGrid:
    """读取设备开放窗口与当天占用，生成六态只读视图对象。

    `conflicted_slots` / `selected_slots` 只用于 409 同页重渲染的展示标记，
    不参与任何状态判定；六个合法状态不变。
    """
    if not equipment_id:
        raise Validation("必须选择设备")

    now_text = now or now_utc()
    day_text = day or utc_to_local(now_text).date().isoformat()

    equipment = equipment_repo.get_by_id(conn, equipment_id)
    if equipment is None or not equipment["active"]:
        raise NotFound("设备不存在")

    slots = build_grid(equipment["open_start"], equipment["open_end"], day_text)
    rows = occupancy_repo.list_for_range(conn, equipment_id, slots[0], slots[-1])
    occupied = {row["slot_start"]: row for row in rows}
    window_end = add_days(now_text, WINDOW_DAYS)
    conflicted = frozenset(conflicted_slots)
    selected = frozenset(selected_slots)

    cells = tuple(
        SlotCell(
            start=start,
            local_time=utc_to_local(start).strftime("%H:%M"),
            state=_resolve_state(start, now_text, window_end, occupied.get(start), viewer_id),
            conflicted=start in conflicted,
            selected=start in selected,
        )
        for start in slots
    )
    # 作用域按"渲染出来的格子是否真的被标脏"判定，而不是按入参集合：
    # 冲突 slot 若不在这一天的网格里（隐藏 date 与 slot 不一致），标脏数为 0，
    # 此时必须退化成整页提示，不能给出一屏 data-conflict="0" 的假清白页。
    if any(cell.conflicted for cell in cells):
        conflict_scope = "cells"
    elif selected:
        conflict_scope = "page"
    else:
        conflict_scope = "none"
    return SlotGrid(
        equipment_id=equipment_id,
        day=day_text,
        open_start=equipment["open_start"],
        open_end=equipment["open_end"],
        cells=cells,
        conflict_scope=conflict_scope,
    )
