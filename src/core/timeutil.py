"""UTC 定长时刻与本地时区转换的唯一入口（ADR-005、R4）。

仓库内只有本文件允许获取当前时刻；时刻一律以 20 字符 UTC 文本出入。
"""

from __future__ import annotations

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
