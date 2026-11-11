"""操作日志只读视图（FR-8、架构 §10.2）。

日志写入由各用例在同一事务内完成；本模块只读，不提供任何 UPDATE/DELETE 路径。
`before_json` / `after_json` 先经 `core/redact.py` 的白名单再过滤后展示。
"""

from __future__ import annotations

from dataclasses import dataclass

from src.core import redact
from src.core.timeutil import utc_to_local
from src.data import audit_repo

DEFAULT_LIMIT = 200
EMPTY = "—"
CREATED_FORMAT = "%Y-%m-%d %H:%M:%S"

ACTION_LABELS = {
    "register": "注册",
    "login_fail": "登录失败",
    "booking_create": "创建预约",
    "booking_cancel": "取消预约",
    "booking_edit": "改单",
    "lock": "锁定",
    "unlock": "解锁",
    "password_reset": "重置密码",
    "user_deactivate": "停用账号",
    "equipment_update": "修改设备",
}
TARGET_LABELS = {"booking": "预约", "equipment": "设备", "user": "用户"}


@dataclass(frozen=True)
class AuditEntry:
    entry_id: int
    actor_id: str
    actor_label: str
    action: str
    action_label: str
    target_type: str
    target_label: str
    target_id: str
    created_at: str
    created_at_display: str
    before_display: str
    after_display: str


@dataclass(frozen=True)
class AuditPage:
    entries: tuple[AuditEntry, ...]
    limit: int
    total: int

    @property
    def truncated(self) -> bool:
        return self.total > len(self.entries)


def _entry(row) -> AuditEntry:
    return AuditEntry(
        entry_id=row["id"],
        actor_id=row["actor_id"],
        actor_label=row["actor_student_no"] or row["actor_id"],
        action=row["action"],
        action_label=ACTION_LABELS.get(row["action"], row["action"]),
        target_type=row["target_type"],
        target_label=TARGET_LABELS.get(row["target_type"], row["target_type"]),
        target_id=row["target_id"],
        created_at=row["created_at"],
        created_at_display=_display_created(row["created_at"]),
        before_display=redact.filter_stored(row["target_type"], row["before_json"]) or EMPTY,
        after_display=redact.filter_stored(row["target_type"], row["after_json"]) or EMPTY,
    )


def _display_created(value) -> str:
    """历史行可能不是 20 字符 UTC 文本；展示失败时原样返回，不让整页 500。"""
    try:
        return utc_to_local(value).strftime(CREATED_FORMAT)
    except (TypeError, ValueError):
        return "" if value is None else str(value)


def list_audit(conn, *, limit=DEFAULT_LIMIT) -> AuditPage:
    """按时间倒序返回最近 `limit` 条日志，附总条数供提示截断。"""
    rows = audit_repo.list_recent(conn, limit)
    return AuditPage(
        entries=tuple(_entry(row) for row in rows),
        limit=limit,
        total=audit_repo.count_all(conn),
    )
