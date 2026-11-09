"""Story 1.1 验收测试：学号注册、登录与管理员重置默认密码。

每条 AC 逐条对应 `_bmad-output/planning-artifacts/epics.md` 的 Story 1.1。
Werkzeug 3.x 移除了 `FlaskClient.cookie_jar` 与 `Map.__getitem__`，
因此用 `has_session_cookie()` / `rule_for()` 表达同样的断言语义。
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

PLAINTEXT = "P@ssw0rd-lab"
DEFAULT_PASSWORD = "lab-default-2026"
CSRF_PATTERN = re.compile(r'name="csrf_token" value="([^"]+)"')


def csrf_token(client, path):
    body = client.get(path).get_data(as_text=True)
    match = CSRF_PATTERN.search(body)
    assert match is not None, f"{path} 未渲染 csrf_token"
    return match.group(1)


def csrf_cookie(client):
    cookie = client.get_cookie("csrf")
    assert cookie is not None, "缺少 csrf cookie"
    return cookie.value


def register(client, student_no, password):
    token = csrf_token(client, "/register")
    return client.post(
        "/register",
        data={"student_no": student_no, "password": password, "csrf_token": token},
    )


def login(client, student_no, password):
    token = csrf_token(client, "/login")
    return client.post(
        "/login",
        data={"student_no": student_no, "password": password, "csrf_token": token},
    )


def has_session_cookie(client):
    return client.get_cookie("session") is not None


def rule_for(app, rule):
    return next(item for item in app.url_map.iter_rules() if item.rule == rule)


def fetch(db_path, sql, params=()):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def count_user(db_path, student_no):
    rows = fetch(db_path, "SELECT COUNT(*) AS n FROM user WHERE student_no = ?", (student_no,))
    return rows[0]["n"]


def user_row(db_path, student_no):
    rows = fetch(db_path, "SELECT * FROM user WHERE student_no = ?", (student_no,))
    assert len(rows) == 1
    return rows[0]


def seed_admin(db_path, student_no, password, user_id="a" * 32):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO user (id, student_no, role, password_hash, password_version, active, created_at)"
            " VALUES (?, ?, 'admin', ?, 1, 1, ?)",
            (user_id, student_no, generate_password_hash(password), "2026-11-09T00:00:00Z"),
        )
        conn.commit()
    finally:
        conn.close()


def test_duplicate_student_no_returns_409_and_keeps_one_row(client, db_path):
    assert register(client, "2025001", PLAINTEXT).status_code == 303

    resp = register(client, "2025001", PLAINTEXT)

    assert resp.status_code == 409 and count_user(db_path, "2025001") == 1


def test_login_success_redirects_and_sets_session_cookie_flags(client, db_path):
    register(client, "2025001", PLAINTEXT)

    resp = login(client, "2025001", PLAINTEXT)
    session_cookies = [
        item for item in resp.headers.getlist("Set-Cookie") if item.startswith("session=")
    ]
    assert len(session_cookies) == 1
    cookie = session_cookies[0]

    assert resp.status_code == 303 and "/equipments" in resp.headers["Location"]
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie and "Path=/" in cookie
    assert has_session_cookie(client)


def test_login_with_wrong_password_returns_401_without_session_cookie(client, db_path):
    register(client, "2025001", PLAINTEXT)

    resp = login(client, "2025001", "wrong-password")

    assert resp.status_code == 401 and not has_session_cookie(client)


def test_anonymous_catalog_and_slot_requests_return_401(client):
    equipments = client.get("/equipments")
    slots = client.get("/slots?equipment_id=E1&date=2026-11-05")

    assert [resp.status_code for resp in (equipments, slots)] == [401, 401]


def test_admin_reset_password_invalidates_old_session(app, db_path):
    student = app.test_client()
    assert register(student, "2025001", PLAINTEXT).status_code == 303
    assert login(student, "2025001", PLAINTEXT).status_code == 303
    assert student.get("/equipments").status_code == 200

    admin = app.test_client()
    seed_admin(db_path, "A0001", "Admin#2026")
    assert login(admin, "A0001", "Admin#2026").status_code == 303

    student_id = user_row(db_path, "2025001")["id"]
    pv_before = user_row(db_path, "2025001")["password_version"]

    reset = admin.post(f"/admin/users/{student_id}/reset-password", data={"csrf_token": csrf_cookie(admin)})
    old_next = student.get("/equipments")
    old_password_login = login(app.test_client(), "2025001", PLAINTEXT)
    new_login = login(app.test_client(), "2025001", DEFAULT_PASSWORD)
    pv_after = user_row(db_path, "2025001")["password_version"]

    assert (reset.status_code, old_next.status_code, new_login.status_code, pv_after - pv_before) == (303, 401, 303, 1)
    assert old_password_login.status_code == 401


def test_reset_password_writes_password_reset_audit(app, db_path):
    student = app.test_client()
    register(student, "2025001", PLAINTEXT)
    login(student, "2025001", PLAINTEXT)

    admin = app.test_client()
    seed_admin(db_path, "A0001", "Admin#2026")
    login(admin, "A0001", "Admin#2026")

    student_id = user_row(db_path, "2025001")["id"]
    pv_before = user_row(db_path, "2025001")["password_version"]
    admin.post(f"/admin/users/{student_id}/reset-password", data={"csrf_token": csrf_cookie(admin)})

    rows = fetch(db_path, "SELECT * FROM audit_log")
    assert [row["action"] for row in rows] == ["password_reset"]
    assert rows[0]["actor_id"] == "a" * 32
    assert rows[0]["target_type"] == "user" and rows[0]["target_id"] == student_id
    assert (rows[0]["before_json"], rows[0]["after_json"]) == (
        '{"password_version": %d}' % pv_before,
        '{"password_version": %d}' % (pv_before + 1),
    )
    assert "password_hash" not in (rows[0]["before_json"] + rows[0]["after_json"])


def test_reset_password_requires_admin(app, db_path):
    student = app.test_client()
    register(student, "2025001", PLAINTEXT)
    login(student, "2025001", PLAINTEXT)
    register(app.test_client(), "2025002", PLAINTEXT)
    target_id = user_row(db_path, "2025002")["id"]

    resp = student.post(f"/admin/users/{target_id}/reset-password", data={"csrf_token": csrf_cookie(student)})

    assert resp.status_code == 403


def test_no_password_recovery_routes(app):
    recovery_rules = {item.rule for item in app.url_map.iter_rules() if "forgot" in item.rule or "recover" in item.rule}

    assert recovery_rules == set() and rule_for(app, "/admin/users/<id>/reset-password").methods == {"POST"}


def test_password_hashes_are_salted_and_plaintext_never_leaks(app, client, db_path, capfd, caplog):
    caplog.set_level(logging.INFO)
    capfd.readouterr()

    first_register = register(client, "2025001", PLAINTEXT)
    second_register = register(client, "2025002", PLAINTEXT)
    assert (first_register.status_code, second_register.status_code) == (303, 303)

    h1 = user_row(db_path, "2025001")["password_hash"]
    h2 = user_row(db_path, "2025002")["password_hash"]

    login_ok = login(client, "2025001", PLAINTEXT)
    assert login_ok.status_code == 303
    wrong_client = app.test_client()
    wrong_login = login(wrong_client, "2025001", "wrong-password")
    assert wrong_login.status_code == 401

    admin = app.test_client()
    seed_admin(db_path, "A0001", "Admin#2026")
    admin_login = login(admin, "A0001", "Admin#2026")
    assert admin_login.status_code == 303
    student_id = user_row(db_path, "2025001")["id"]
    reset = admin.post(
        f"/admin/users/{student_id}/reset-password", data={"csrf_token": csrf_cookie(admin)}
    )
    assert reset.status_code == 303

    bodies = [
        resp.get_data(as_text=True)
        for resp in (first_register, second_register, login_ok, wrong_login, admin_login, reset)
    ]

    captured = capfd.readouterr()
    haystack = h1 + h2 + "".join(bodies) + captured.out + captured.err + caplog.text

    assert h1 != h2 and h1 != PLAINTEXT and h2 != PLAINTEXT and PLAINTEXT not in haystack


def test_post_without_csrf_token_is_rejected(client):
    resp = client.post("/login", data={"student_no": "2025001", "password": PLAINTEXT})

    assert resp.status_code == 400


def test_csrf_token_from_another_client_is_rejected(app):
    attacker = app.test_client()
    attacker_token = csrf_token(attacker, "/login")
    victim = app.test_client()
    csrf_token(victim, "/login")

    assert attacker.get_cookie("csrf") is not None
    assert victim.get_cookie("csrf") is not None
    assert attacker.get_cookie("csrf").value != victim.get_cookie("csrf").value

    resp = victim.post(
        "/login",
        data={"student_no": "2025001", "password": PLAINTEXT, "csrf_token": attacker_token},
    )

    assert resp.status_code == 400


def test_tampered_csrf_cookie_is_rejected(client):
    client.set_cookie("csrf", "attacker-chosen-token")

    resp = client.post(
        "/login",
        data={"student_no": "2025001", "password": PLAINTEXT, "csrf_token": "attacker-chosen-token"},
    )

    assert resp.status_code == 400


def test_csrf_rejection_does_not_issue_session_cookie(client):
    resp = client.post("/login", data={"student_no": "2025001", "password": PLAINTEXT})

    assert resp.status_code == 400 and not has_session_cookie(client)


def test_reset_password_rejects_admin_target(app, db_path):
    admin = app.test_client()
    seed_admin(db_path, "A0001", "Admin#2026", user_id="a" * 32)
    seed_admin(db_path, "A0002", "Admin#2026", user_id="b" * 32)
    assert login(admin, "A0001", "Admin#2026").status_code == 303
    target = user_row(db_path, "A0002")

    resp = admin.post(
        f"/admin/users/{target['id']}/reset-password", data={"csrf_token": csrf_cookie(admin)}
    )

    assert resp.status_code == 400
    assert "学生" in resp.get_data(as_text=True)
    assert user_row(db_path, "A0002")["password_version"] == target["password_version"]
    assert fetch(db_path, "SELECT * FROM audit_log") == []


def test_integrity_error_is_classified_by_sqlite_errorname(monkeypatch, client):
    from src.data import user_repo

    def raise_foreign_key(*args, **kwargs):
        error = sqlite3.IntegrityError("UNIQUE constraint failed: user.student_no")
        error.sqlite_errorname = "SQLITE_CONSTRAINT_FOREIGNKEY"
        raise error

    monkeypatch.setattr(user_repo, "insert_user", raise_foreign_key)
    token = csrf_token(client, "/register")

    with pytest.raises(sqlite3.IntegrityError):
        client.post(
            "/register",
            data={"student_no": "2025001", "password": PLAINTEXT, "csrf_token": token},
        )


def test_apply_migrations_runs_inside_write_tx(monkeypatch, tmp_path):
    from src.data import migrations

    calls = []
    real_write_tx = migrations.write_tx

    @contextmanager
    def spy(conn):
        calls.append(conn)
        with real_write_tx(conn):
            yield conn

    monkeypatch.setattr(migrations, "write_tx", spy)
    conn = sqlite3.connect(str(tmp_path / "migrations.db"), isolation_level=None)
    migrations_dir = Path(__file__).resolve().parents[1] / "migrations"
    try:
        migrations.apply_migrations(conn, migrations_dir)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
        assert conn.execute("SELECT name FROM sqlite_master WHERE name = 'user'").fetchone() is not None
        migrations.apply_migrations(conn, migrations_dir)
    finally:
        conn.close()

    assert len(calls) == 1


def test_migration_allows_multiple_statements_on_one_line(tmp_path):
    from src.data import migrations

    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    (migration_dir / "001_multi.sql").write_text(
        "CREATE TABLE a (id INTEGER); CREATE TABLE b (id INTEGER);\n",
        encoding="utf-8",
    )
    conn = sqlite3.connect(str(tmp_path / "migrations.db"), isolation_level=None)
    try:
        migrations.apply_migrations(conn, migration_dir)

        names = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert {"a", "b"} <= names
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    finally:
        conn.close()


def test_failed_migration_leaves_no_partial_schema(tmp_path):
    from src.data import migrations

    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    (migration_dir / "001_bad.sql").write_text(
        "CREATE TABLE first_table (id INTEGER);\n"
        "CREATE TABLE broken (id INTEGER, );\n",
        encoding="utf-8",
    )
    conn = sqlite3.connect(str(tmp_path / "migrations.db"), isolation_level=None)
    try:
        with pytest.raises(sqlite3.OperationalError):
            migrations.apply_migrations(conn, migration_dir)

        assert conn.execute("SELECT name FROM sqlite_master WHERE name = 'first_table'").fetchone() is None
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
        assert not conn.in_transaction
    finally:
        conn.close()


def test_redact_whitelist_covers_booking_and_equipment():
    from src.core import redact

    booking = {
        "owner_id": "u" * 32,
        "equipment_id": "E1",
        "slots": ["2026-11-05T06:00:00Z"],
        "created_at": "2026-11-09T00:00:00Z",
        "updated_at": "2026-11-09T00:00:00Z",
    }
    equipment = {
        "name": "显微镜",
        "open_start": "09:00",
        "open_end": "12:00",
        "active": 1,
        "slots": ["2026-11-05T06:00:00Z"],
    }

    assert json.loads(redact.dump_fields("booking", booking)) == booking
    assert json.loads(redact.dump_fields("equipment", equipment)) == equipment
    with pytest.raises(ValueError):
        redact.dump_fields("booking", {"password_hash": "secret"})


def test_register_template_does_not_duplicate_password_length_rule(client):
    body = client.get("/register").get_data(as_text=True)

    assert "minlength" not in body


def test_register_rejects_password_shorter_than_eight(client, db_path):
    resp = register(client, "2025001", "1234567")

    assert resp.status_code == 400 and count_user(db_path, "2025001") == 0


def test_anonymous_register_page_issues_bound_csrf_cookie(client):
    resp = client.get("/register")
    set_cookies = [
        item for item in resp.headers.getlist("Set-Cookie") if item.startswith("csrf=")
    ]
    assert len(set_cookies) == 1
    token = CSRF_PATTERN.search(resp.get_data(as_text=True)).group(1)

    assert "HttpOnly" in set_cookies[0] and "SameSite=Lax" in set_cookies[0]
    assert "Path=/" in set_cookies[0] and "Max-Age=" in set_cookies[0]
    assert client.get_cookie("csrf").value == token


def test_login_and_logout_rotate_csrf_token(client, db_path):
    assert register(client, "2025001", PLAINTEXT).status_code == 303
    before_login = csrf_cookie(client)
    assert login(client, "2025001", PLAINTEXT).status_code == 303
    after_login = csrf_cookie(client)
    assert after_login != before_login

    stale = client.post("/logout", data={"csrf_token": before_login})
    assert stale.status_code == 400

    before_logout = csrf_cookie(client)
    logout = client.post("/logout", data={"csrf_token": before_logout})
    assert logout.status_code == 303
    assert csrf_cookie(client) != before_logout
