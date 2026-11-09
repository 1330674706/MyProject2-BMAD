"""Story 1.1 验收测试：学号注册、登录与管理员重置默认密码。

每条 AC 逐条对应 `_bmad-output/planning-artifacts/epics.md` 的 Story 1.1。
Werkzeug 3.x 移除了 `FlaskClient.cookie_jar` 与 `Map.__getitem__`，
因此用 `has_session_cookie()` / `rule_for()` 表达同样的断言语义。
"""

from __future__ import annotations

import logging
import re
import sqlite3

from werkzeug.security import generate_password_hash

PLAINTEXT = "P@ssw0rd-lab"
DEFAULT_PASSWORD = "lab-default-2026"
CSRF_PATTERN = re.compile(r'name="csrf_token" value="([^"]+)"')


def csrf_token(client, path):
    body = client.get(path).get_data(as_text=True)
    match = CSRF_PATTERN.search(body)
    assert match is not None, f"{path} 未渲染 csrf_token"
    return match.group(1)


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


def seed_admin(db_path, student_no, password):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO user (id, student_no, role, password_hash, password_version, active, created_at)"
            " VALUES (?, ?, 'admin', ?, 1, 1, ?)",
            ("a" * 32, student_no, generate_password_hash(password), "2026-11-09T00:00:00Z"),
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
    cookie = resp.headers.get("Set-Cookie", "")

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
    with admin.session_transaction() as session:
        token = session["csrf_token"]

    reset = admin.post(f"/admin/users/{student_id}/reset-password", data={"csrf_token": token})
    old_next = student.get("/equipments")
    new_login = login(student, "2025001", DEFAULT_PASSWORD)
    pv_after = user_row(db_path, "2025001")["password_version"]

    assert (reset.status_code, old_next.status_code, new_login.status_code, pv_after - pv_before) == (303, 401, 303, 1)


def test_reset_password_writes_password_reset_audit(app, db_path):
    student = app.test_client()
    register(student, "2025001", PLAINTEXT)
    login(student, "2025001", PLAINTEXT)

    admin = app.test_client()
    seed_admin(db_path, "A0001", "Admin#2026")
    login(admin, "A0001", "Admin#2026")
    with admin.session_transaction() as session:
        token = session["csrf_token"]

    student_id = user_row(db_path, "2025001")["id"]
    pv_before = user_row(db_path, "2025001")["password_version"]
    admin.post(f"/admin/users/{student_id}/reset-password", data={"csrf_token": token})

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
    with student.session_transaction() as session:
        token = session["csrf_token"]

    resp = student.post(f"/admin/users/{target_id}/reset-password", data={"csrf_token": token})

    assert resp.status_code == 403


def test_no_password_recovery_routes(app):
    recovery_rules = {item.rule for item in app.url_map.iter_rules() if "forgot" in item.rule or "recover" in item.rule}

    assert recovery_rules == set() and rule_for(app, "/admin/users/<id>/reset-password").methods == {"POST"}


def test_password_hashes_are_salted_and_plaintext_never_leaks(app, client, db_path, capfd, caplog):
    caplog.set_level(logging.INFO)
    capfd.readouterr()

    bodies = [
        register(client, "2025001", PLAINTEXT).get_data(as_text=True),
        register(client, "2025002", PLAINTEXT).get_data(as_text=True),
    ]
    h1 = user_row(db_path, "2025001")["password_hash"]
    h2 = user_row(db_path, "2025002")["password_hash"]

    bodies.append(login(client, "2025001", PLAINTEXT).get_data(as_text=True))
    wrong_client = app.test_client()
    bodies.append(login(wrong_client, "2025001", "wrong-password").get_data(as_text=True))

    admin = app.test_client()
    seed_admin(db_path, "A0001", "Admin#2026")
    bodies.append(login(admin, "A0001", "Admin#2026").get_data(as_text=True))
    with admin.session_transaction() as session:
        token = session["csrf_token"]
    student_id = user_row(db_path, "2025001")["id"]
    bodies.append(
        admin.post(f"/admin/users/{student_id}/reset-password", data={"csrf_token": token}).get_data(as_text=True)
    )

    captured = capfd.readouterr()
    haystack = h1 + h2 + "".join(bodies) + captured.out + captured.err + caplog.text

    assert h1 != h2 and h1 != PLAINTEXT and h2 != PLAINTEXT and PLAINTEXT not in haystack


def test_post_without_csrf_token_is_rejected(client):
    resp = client.post("/login", data={"student_no": "2025001", "password": PLAINTEXT})

    assert resp.status_code == 400