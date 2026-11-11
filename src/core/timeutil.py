"""UTC 定长时刻与本地时区转换的唯一入口（ADR-005、R4）。

仓库内只有本文件允许获取当前时刻；时刻一律以 20 字符 UTC 文本出入。
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
LOCAL_TZ = ZoneInfo("Asia/Shanghai")


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime(UTC_FORMAT)


def parse_utc(value: str) -> datetime:
    """20 字符 UTC 文本转带 UTC 时区的 datetime。"""
    return datetime.strptime(value, UTC_FORMAT).replace(tzinfo=timezone.utc)


def add_days(value: str, days: int) -> str:
    """UTC 文本加自然天数，返回新的 20 字符 UTC 文本。"""
    return (parse_utc(value) + timedelta(days=days)).strftime(UTC_FORMAT)


def add_minutes_utc(value: str, minutes: int) -> str:
    """UTC 文本加分钟数，返回新的 20 字符 UTC 文本（slot 结束时刻由服务端算）。"""
    return (parse_utc(value) + timedelta(minutes=minutes)).strftime(UTC_FORMAT)


def strictly_later_utc(previous: str, candidate: str) -> str:
    """返回严格晚于 previous 的 UTC 文本；同一秒内至少前进 1 秒。"""
    previous_moment = parse_utc(previous)
    if parse_utc(candidate) > previous_moment:
        return candidate
    return (previous_moment + timedelta(seconds=1)).strftime(UTC_FORMAT)


def local_at(day: str, wallclock: str) -> datetime:
    """把本地日期与 `HH:MM` 墙钟组合成带时区的本地时刻。"""
    return datetime.combine(
        date.fromisoformat(day),
        time.fromisoformat(wallclock),
        tzinfo=LOCAL_TZ,
    )


def local_to_utc(local_dt: datetime) -> str:
    """本地时刻转 20 字符 UTC 文本；无时区输入按 Asia/Shanghai 解释。"""
    if local_dt.tzinfo is None:
        local_dt = local_dt.replace(tzinfo=LOCAL_TZ)
    else:
        local_dt = local_dt.astimezone(LOCAL_TZ)
    return local_dt.astimezone(timezone.utc).strftime(UTC_FORMAT)


def utc_to_local(value: str) -> datetime:
    """20 字符 UTC 文本转 Asia/Shanghai 本地时刻。"""
    return parse_utc(value).astimezone(LOCAL_TZ)


def week_bounds_utc(value: str | None = None, *, now: str | None = None) -> tuple[str, str, str]:
    """返回 `(周一本地日期, 周起始 UTC, 下周起始 UTC)`，右端开区间。

    `value` 接受 `YYYY-MM-DD`（该周内任意一天）或 `YYYY-Www`；缺省取当前周。
    """
    text = (value or "").strip()
    if not text:
        anchor = utc_to_local(now or now_utc()).date()
    elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        anchor = date.fromisoformat(text)
    elif re.fullmatch(r"\d{4}-W\d{2}", text):
        anchor = date.fromisocalendar(int(text[:4]), int(text[6:]), 1)
    else:
        raise ValueError("周参数必须是 YYYY-MM-DD 或 YYYY-Www")

    monday = anchor - timedelta(days=anchor.weekday())
    try:
        start = local_to_utc(local_at(monday.isoformat(), "00:00"))
        end = local_to_utc(local_at((monday + timedelta(days=7)).isoformat(), "00:00"))
    except (ValueError, OverflowError):
        raise ValueError("周参数超出支持范围") from None
    return monday.isoformat(), start, end
