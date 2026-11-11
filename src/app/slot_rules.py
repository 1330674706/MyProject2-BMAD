"""slot 形状与可约窗口校验的唯一落点（FR-4、§11）。"""

from __future__ import annotations

import re
from datetime import time, timedelta

from src.core.errors import Validation
from src.core.timeutil import parse_utc, utc_to_local

SLOT_MINUTES = 30
MAX_SLOTS = 8
WINDOW_DAYS = 7
CANCEL_LEAD_HOURS = 2
CANCEL_STATUS_CANCELLABLE = "cancellable"
CANCEL_STATUS_STARTED = "started"
CANCEL_STATUS_PAST_DEADLINE = "past_deadline"

UTC_SLOT_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:00Z$")
VALID_MODES = ("create", "edit")


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


def validate(equipment, slots, now, *, mode="create", current_first_slot=None):
    """校验 1–8 个连续、对齐、在开放窗口与 7 天窗口内的未来 slot。

    create/edit 共用同一套形状规则；只有 edit 额外执行首个 slot 前 2 小时截止。
    `current_first_slot` 仅供 edit 使用且必填：edit 同时约束原预约与目标的首个 slot。
    """
    if mode not in VALID_MODES:
        raise ValueError(f"未知校验模式: {mode}")
    if mode == "edit" and current_first_slot is None:
        raise ValueError("edit 模式必须提供原预约的首个 slot")
    if mode == "create" and current_first_slot is not None:
        raise ValueError("create 模式不接受 current_first_slot")
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
    window_end = now_moment + timedelta(days=WINDOW_DAYS)
    for moment in moments:
        if moment <= now_moment:
            raise Validation("所选 slot 已开始")
        if moment > window_end:
            raise Validation("所选 slot 超出可约窗口")
    if mode == "edit":
        edit_starts = [moments[0], _parse_slot(current_first_slot)]
        deadline = timedelta(hours=CANCEL_LEAD_HOURS)
        if any(start - now_moment < deadline for start in edit_starts):
            raise Validation(f"改单需在首个 slot 开始前至少 {CANCEL_LEAD_HOURS} 小时")
    return list(slots)


def cancel_status(first_slot, now):
    """取消状态：cancellable / started / past_deadline（FR-6）。"""
    try:
        first_moment = parse_utc(first_slot) if isinstance(first_slot, str) else first_slot
        now_moment = parse_utc(now) if isinstance(now, str) else now
    except ValueError:
        raise Validation("slot 时刻不存在") from None
    if first_moment <= now_moment:
        return CANCEL_STATUS_STARTED
    if first_moment - now_moment < timedelta(hours=CANCEL_LEAD_HOURS):
        return CANCEL_STATUS_PAST_DEADLINE
    return CANCEL_STATUS_CANCELLABLE


def _unique_aligned_slots(slots):
    """校验形状并去重保序；重复 slot 只保留一次，避免自撞唯一键。"""
    unique = []
    for raw in slots:
        moment = _parse_slot(raw)
        if moment.minute % SLOT_MINUTES != 0 or moment.second != 0:
            raise Validation("slot 必须对齐到整点或半点")
        if raw not in unique:
            unique.append(raw)
    return unique


def validate_lock_slots(equipment, slots, now):
    """锁定接受 1+ 个未来 7 天内、开放窗口内的对齐 slot；不要求连续。"""
    if not slots:
        raise Validation("请至少选择 1 个 slot")
    normalized = _unique_aligned_slots(slots)
    open_start, open_end = _open_window(equipment)
    now_moment = parse_utc(now) if isinstance(now, str) else now
    window_end = now_moment + timedelta(days=WINDOW_DAYS)
    for raw in normalized:
        moment = _parse_slot(raw)
        if not (open_start <= utc_to_local(raw).time() < open_end):
            raise Validation("slot 不在设备开放时间内")
        if moment <= now_moment:
            raise Validation("不能锁定已开始的 slot")
        if moment > window_end:
            raise Validation("所选 slot 超出可锁窗口")
    return normalized


def validate_unlock_slots(slots):
    """解锁只校验形状：允许清理已经过去或滑出窗口的历史锁。"""
    if not slots:
        raise Validation("请至少选择 1 个 slot")
    return _unique_aligned_slots(slots)


def validate_cancellable(first_slot, now):
    """取消截止：首个 slot 开始前至少 2 小时（FR-6）。"""
    status = cancel_status(first_slot, now)
    if status == CANCEL_STATUS_STARTED:
        raise Validation("预约已开始，无法取消")
    if status == CANCEL_STATUS_PAST_DEADLINE:
        raise Validation(f"距首个 slot 开始不足 {CANCEL_LEAD_HOURS} 小时，无法取消")
