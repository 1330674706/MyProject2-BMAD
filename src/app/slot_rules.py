"""slot 形状与可约窗口校验的唯一落点（FR-4、§11）。"""

from __future__ import annotations

import re
from datetime import time, timedelta

from src.core.errors import Validation
from src.core.timeutil import parse_utc, utc_to_local

SLOT_MINUTES = 30
MAX_SLOTS = 8
WINDOW_DAYS = 7

UTC_SLOT_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:00Z$")


def _parse_slot(raw):
    if not isinstance(raw, str) or UTC_SLOT_PATTERN.fullmatch(raw) is None:
        raise Validation("slot 必须是 YYYY-MM-DDTHH:MM:SSZ 格式")
    try:
        return parse_utc(raw)
    except ValueError:
        raise Validation("slot 时刻不存在") from None


def _open_window(equipment):
    try:
        return time.fromisoformat(equipment["open_start"]), time.fromisoformat(equipment["open_end"])
    except (KeyError, TypeError, ValueError):
        raise Validation("设备开放时间配置不正确") from None


def validate_slots(equipment, slots, now):
    """校验 1–8 个连续、对齐、在开放窗口与 7 天窗口内的未来 slot。"""
    if not slots:
        raise Validation("请至少选择 1 个 slot")
    if len(slots) > MAX_SLOTS:
        raise Validation("一次最多预约 8 个连续 slot")

    moments = [_parse_slot(raw) for raw in slots]
    for moment in moments:
        if moment.minute % SLOT_MINUTES != 0 or moment.second != 0:
            raise Validation("slot 必须对齐到整点或半点")
    for previous, current in zip(moments, moments[1:]):
        if current - previous != timedelta(minutes=SLOT_MINUTES):
            raise Validation("所选的 slot 必须连续")

    open_start, open_end = _open_window(equipment)
    for raw in slots:
        if not (open_start <= utc_to_local(raw).time() < open_end):
            raise Validation("slot 不在设备开放时间内")

    now_moment = parse_utc(now) if isinstance(now, str) else now
    if moments[0] <= now_moment:
        raise Validation("首个 slot 已经开始")
    if moments[0] > now_moment + timedelta(days=WINDOW_DAYS):
        raise Validation("首个 slot 超出 7 天可预约窗口")
    return list(slots)
