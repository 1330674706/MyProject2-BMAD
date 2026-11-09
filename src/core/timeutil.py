"""UTC 定长时刻与本地时区转换的唯一入口（ADR-005、R4）。

仓库内只有本文件允许获取当前时刻；时刻一律以 20 字符 UTC 文本出入。
"""

from __future__ import annotations

from datetime import datetime, timezone

UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime(UTC_FORMAT)