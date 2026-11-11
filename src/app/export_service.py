"""自然周 CSV 导出（FR-8、ADR-005、架构 §10.1）。

六列固定、一行一个 slot、UTF-8 BOM；slot 结束时刻由服务端按 30 分钟推算，
时刻统一从 UTC 转成 Asia/Shanghai 本地墙钟再输出。
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass

from src.app import slot_service
from src.app.slot_rules import SLOT_MINUTES
from src.core.errors import Validation
from src.core.timeutil import add_minutes_utc, utc_to_local, week_bounds_utc
from src.data import booking_repo

CSV_HEADER = ("设备", "slot 开始", "slot 结束", "学号", "booking_id", "状态")
EXPORT_STATUS = "有效"
WALLCLOCK_FORMAT = "%Y-%m-%d %H:%M"


@dataclass(frozen=True)
class ExportFile:
    filename: str
    body: bytes


FORMULA_PREFIXES = ("=", "+", "-", "@")


def _csv_cell(value) -> str:
    """中和换行与电子表格公式前缀，保证一行仍是一个 slot。"""
    text = "" if value is None else str(value)
    text = text.replace("\r", " ").replace("\n", " ")
    if text.startswith(FORMULA_PREFIXES):
        return "'" + text
    return text


def _wallclock(value: str) -> str:
    return utc_to_local(value).strftime(WALLCLOCK_FORMAT)


def build_week_export(conn, *, week=None, now=None) -> ExportFile:
    """生成指定自然周的 CSV；周参数非法时抛 Validation，由 web 层映射 400。"""
    now_text = now or slot_service.now_utc()
    try:
        monday, start_utc, end_utc = week_bounds_utc(week, now=now_text)
    except ValueError as error:
        raise Validation(str(error)) from None

    rows = booking_repo.list_week_export_rows(conn, start_utc, end_utc)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_HEADER)
    for row in rows:
        writer.writerow(
            (
                _csv_cell(row["equipment_name"]),
                _csv_cell(_wallclock(row["slot_start"])),
                _csv_cell(_wallclock(add_minutes_utc(row["slot_start"], SLOT_MINUTES))),
                _csv_cell(row["student_no"]),
                _csv_cell(row["booking_id"]),
                _csv_cell(EXPORT_STATUS),
            )
        )
    return ExportFile(
        filename=f"bookings-{monday}.csv",
        body=buffer.getvalue().encode("utf-8-sig"),
    )
