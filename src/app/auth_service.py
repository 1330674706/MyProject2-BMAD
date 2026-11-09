"""账号用例：注册、登录、重置默认密码（FR-1、ADR-004、§5.5）。

业务规则只在这里实现；web/ 只解析表单并映射状态码（R1）。
"""

from __future__ import annotations

import sqlite3

from werkzeug.security import check_password_hash, generate_password_hash

from src.core import redact
from src.core.errors import Conflict, NotFound, Unauthorized, Validation
from src.core.ids import new_id
from src.core.timeutil import now_utc
from src.data import audit_repo, user_repo
from src.data.tx import write_tx

MIN_PASSWORD_LENGTH = 8


def register(conn, *, student_no, password):
    student_no = (student_no or "").strip()
    if not student_no:
        raise Validation("学号不能为空")
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        raise Validation(f"密码至少 {MIN_PASSWORD_LENGTH} 位")

    user_id = new_id()
    password_hash = generate_password_hash(password)
    try:
        with write_tx(conn):
            user_repo.insert_user(
                conn,
                user_id=user_id,
                student_no=student_no,
                role="student",
                password_hash=password_hash,
                created_at=now_utc(),
            )
    except sqlite3.IntegrityError as error:
        if "user.student_no" not in str(error):
            raise
        raise Conflict("该学号已注册") from None
    return user_repo.get_by_id(conn, user_id)


def login(conn, *, student_no, password):
    user = user_repo.get_by_student_no(conn, (student_no or "").strip())
    if user is None or not user["active"]:
        raise Unauthorized("学号或密码不正确")
    if not password or not check_password_hash(user["password_hash"], password):
        raise Unauthorized("学号或密码不正确")
    return user


def reset_password(conn, *, target_user_id, actor_id, default_password):
    password_hash = generate_password_hash(default_password)
    with write_tx(conn):
        target = user_repo.get_by_id(conn, target_user_id)
        if target is None:
            raise NotFound("用户不存在")

        version_before = target["password_version"]
        if user_repo.update_password(conn, user_id=target_user_id, password_hash=password_hash) != 1:
            raise NotFound("用户不存在")
        audit_repo.insert_audit(
            conn,
            actor_id=actor_id,
            action="password_reset",
            target_type="user",
            target_id=target_user_id,
            before_json=redact.dump_fields("user", {"password_version": version_before}),
            after_json=redact.dump_fields("user", {"password_version": version_before + 1}),
            created_at=now_utc(),
        )


def current_user(conn, *, uid, pv):
    if not uid or pv is None:
        return None
    user = user_repo.get_by_id(conn, uid)
    if user is None or not user["active"]:
        return None
    if user["password_version"] != pv:
        return None
    return user