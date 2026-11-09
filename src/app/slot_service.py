"""slot 派生：开放时间到 UTC slot 集合的唯一生产者（FR-2、ADR-005）。

slot 是派生量，不建表；本模块只负责时间形状，不读取占用状态。
"""

from __future__ import annotations

from datetime import timedelta

from src.core.errors import Validation
from src.core.timeutil import local_at, local_to_utc

SLOT_MINUTES = 30


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
