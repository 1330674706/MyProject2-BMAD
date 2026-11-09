"""python -m src.seed：从 seed/equipment.csv 幂等导入设备（FR-2），
并按环境变量幂等创建管理员账号（Story 1.4）。
"""

from __future__ import annotations

import csv
import os
import sqlite3
import sys
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

from src.app.equipment_service import prepare_equipment_rows, write_equipment_rows
from src.core.config import resolve_db_path
from src.core.errors import AppError
from src.core.ids import new_id
from src.core.timeutil import now_utc
from src.data import user_repo
from src.data.db import connect, initialize
from src.data.tx import write_tx

SEED_PATH = Path("seed") / "equipment.csv"
EXPECTED_COLUMNS = ["equipment_id", "name", "open_start", "open_end"]
ADMIN_USER_ENV = "LAB_ADMIN_USER"
ADMIN_PASSWORD_ENV = "LAB_ADMIN_PASSWORD"

UPSERT_ADMIN = (
    "INSERT INTO user (id, student_no, role, password_hash, password_version, active, created_at)"
    " VALUES (?, ?, 'admin', ?, 1, 1, ?)"
    " ON CONFLICT(student_no) DO UPDATE SET"
    " role = 'admin',"
    " password_hash = excluded.password_hash,"
    " password_version = password_version + 1,"
    " active = 1"
)


class SeedError(RuntimeError):
    """种子文件结构不合法；进程必须非 0 退出且不落任何数据。"""


def read_admin_credentials(environ=None):
    """读取管理员种子变量；缺失返回 (None, 缺失变量名列表)，不视为错误。"""
    env = os.environ if environ is None else environ
    student_no = (env.get(ADMIN_USER_ENV) or "").strip()
    password = env.get(ADMIN_PASSWORD_ENV) or ""
    missing = [
        name
        for name, value in ((ADMIN_USER_ENV, student_no), (ADMIN_PASSWORD_ENV, password))
        if not value
    ]
    if missing:
        return None, missing
    return (student_no, password), []


def write_admin(conn, credentials) -> str:
    """按学号 upsert 管理员；未变化时不写库。返回 new/updated/unchanged。"""
    student_no, password = credentials
    with write_tx(conn):
        current = user_repo.get_by_student_no(conn, student_no)
        if (
            current is not None
            and current["role"] == "admin"
            and current["active"] == 1
            and check_password_hash(current["password_hash"], password)
        ):
            return "unchanged"
        conn.execute(
            UPSERT_ADMIN,
            (new_id(), student_no, generate_password_hash(password), now_utc()),
        )
    return "new" if current is None else "updated"


def read_equipment_rows(path: Path):
    try:
        handle = path.open("r", encoding="utf-8-sig", newline="")
    except FileNotFoundError:
        raise SeedError(f"找不到种子文件：{path}") from None
    except OSError as error:
        raise SeedError(f"无法读取种子文件 {path}：{error}") from None

    try:
        with handle:
            reader = csv.reader(handle)
            header = next(reader, None)
            if header != EXPECTED_COLUMNS:
                shown = ",".join(header) if header else "空文件"
                raise SeedError(
                    f"种子文件 {path} 表头必须是 {','.join(EXPECTED_COLUMNS)}，实际为 {shown}"
                )
            rows = []
            for record in reader:
                line_no = reader.line_num
                if not any(field.strip() for field in record):
                    continue
                if len(record) != len(EXPECTED_COLUMNS):
                    raise SeedError(
                        f"第 {line_no} 行: 需要 {len(EXPECTED_COLUMNS)} 列，实际 {len(record)} 列"
                    )
                rows.append((line_no, *record))
            return rows
    except UnicodeDecodeError:
        raise SeedError(f"种子文件必须是 UTF-8 编码：{path}") from None


def main() -> int:
    db_path = resolve_db_path()
    credentials, missing = read_admin_credentials()
    if credentials is None:
        print(
            f"提示：未设置 {' / '.join(missing)}，跳过管理员种子。",
            file=sys.stderr,
        )
    try:
        rows = read_equipment_rows(SEED_PATH)
        prepared = prepare_equipment_rows(rows)
        initialize(db_path)
        conn = connect(db_path)
        try:
            count = write_equipment_rows(conn, prepared)
            admin_state = None if credentials is None else write_admin(conn, credentials)
        finally:
            conn.close()
    except (SeedError, AppError, sqlite3.Error, OSError) as error:
        print(f"种子导入失败：{error}")
        return 1
    print(f"种子导入完成：{count} 台设备 -> {db_path}")
    if admin_state is not None:
        print(f"管理员种子完成：{credentials[0]}（{admin_state}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
