"""Story 1.2 验收测试：设备清单、开放时间维护与 slot 派生。

每条 AC 逐条对应 `_bmad-output/planning-artifacts/epics.md` 的 Story 1.2。
测试只通过公开入口（`build_grid()` 与 HTTP 路由）观察行为，不复制服务层逻辑。
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime

from werkzeug.security import generate_password_hash

PLAINTEXT = "P@ssw0rd-lab"
ADMIN_PASSWORD = "Admin#2026"
DAY = "2030-01-01"
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


def login_student(app, student_no="2025001"):
    client = app.test_client()
    assert register(client, student_no, PLAINTEXT).status_code == 303
    assert login(client, student_no, PLAINTEXT).status_code == 303
    return client


def connect(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def seed_admin(db_path, student_no="A0001", password=ADMIN_PASSWORD, user_id="a" * 32):
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO user (id, student_no, role, password_hash, password_version, active, created_at)"
            " VALUES (?, ?, 'admin', ?, 1, 1, ?)",
            (user_id, student_no, generate_password_hash(password), "2026-11-09T00:00:00Z"),
        )
        conn.commit()
    finally:
        conn.close()


def seed_equipment(db_path, equipment_id="E1", name="显微镜", open_start="09:00", open_end="12:00"):
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO equipment (id, name, open_start, open_end, active) VALUES (?, ?, ?, ?, 1)",
            (equipment_id, name, open_start, open_end),
        )
        conn.commit()
    finally:
        conn.close()


def equipment_row(db_path, equipment_id="E1"):
    conn = connect(db_path)
    try:
        return conn.execute("SELECT * FROM equipment WHERE id = ?", (equipment_id,)).fetchone()
    finally:
        conn.close()


def occupancy_count(db_path, equipment_id="E1"):
    conn = connect(db_path)
    try:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM occupancy WHERE equipment_id = ?", (equipment_id,)
        ).fetchone()["n"]
    finally:
        conn.close()


def audit_count(db_path, action="equipment_update"):
    conn = connect(db_path)
    try:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM audit_log WHERE action = ?", (action,)
        ).fetchone()["n"]
    finally:
        conn.close()


def seed_raw_occupancy(db_path, slot_start, equipment_id="E1"):
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO occupancy (equipment_id, slot_start, kind, booking_id, created_at)"
            " VALUES (?, ?, 'lock', NULL, ?)",
            (equipment_id, slot_start, "2026-11-09T00:00:00Z"),
        )
        conn.commit()
    finally:
        conn.close()


def utc_at(day, hhmm):
    from src.core.timeutil import local_to_utc

    return local_to_utc(datetime.fromisoformat(f"{day}T{hhmm}:00"))


def seed_booking_occupancy(db_path, times, equipment_id="E1", day=DAY):
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO user (id, student_no, role, password_hash, password_version, active, created_at)"
            " VALUES (?, ?, 'student', ?, 1, 1, ?)",
            ("s" * 32, "2025999", generate_password_hash(PLAINTEXT), "2026-11-09T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO booking (id, owner_id, equipment_id, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?)",
            ("b" * 32, "s" * 32, equipment_id, "2026-11-09T00:00:00Z", "2026-11-09T00:00:00Z"),
        )
        for hhmm in times:
            conn.execute(
                "INSERT INTO occupancy (equipment_id, slot_start, kind, booking_id, created_at)"
                " VALUES (?, ?, 'booking', ?, ?)",
                (equipment_id, utc_at(day, hhmm), "b" * 32, "2026-11-09T00:00:00Z"),
            )
        conn.commit()
    finally:
        conn.close()


def admin_client(app, db_path):
    seed_admin(db_path)
    client = app.test_client()
    assert login(client, "A0001", ADMIN_PASSWORD).status_code == 303
    return client


def post_window(client, equipment_id, open_start, open_end):
    return client.post(
        f"/admin/equipments/{equipment_id}/window",
        data={
            "open_start": open_start,
            "open_end": open_end,
            "csrf_token": csrf_cookie(client),
        },
    )


def test_build_grid_0900_to_1200_yields_six_slots():
    from src.app.slot_service import build_grid
    from src.core.timeutil import utc_to_local

    grid = build_grid("09:00", "12:00", DAY)

    assert [utc_to_local(s).strftime("%H:%M") for s in grid] == [
        "09:00",
        "09:30",
        "10:00",
        "10:30",
        "11:00",
        "11:30",
    ]


def test_build_grid_0800_to_2200_yields_twenty_eight_slots():
    from src.app.slot_service import build_grid
    from src.core.timeutil import utc_to_local

    grid = build_grid("08:00", "22:00", DAY)
    first = utc_to_local(grid[0]).strftime("%H:%M")
    last = utc_to_local(grid[-1]).strftime("%H:%M")

    assert len(grid) == 28 and first == "08:00" and last == "21:30"


def test_narrowing_window_over_existing_occupancy_returns_409_without_change(app, db_path):
    seed_equipment(db_path, open_start="08:00", open_end="22:00")
    seed_booking_occupancy(db_path, ["15:00", "15:30"])
    admin = admin_client(app, db_path)
    n_before = occupancy_count(db_path)
    open_end_before = equipment_row(db_path)["open_end"]

    resp = post_window(admin, "E1", "08:00", "15:00")
    open_end_after = equipment_row(db_path)["open_end"]

    assert resp.status_code == 409 and open_end_after == open_end_before and occupancy_count(db_path) == n_before
    body = resp.get_data(as_text=True)
    assert "E1" in body and f"{DAY}T07:00:00Z" in body and audit_count(db_path) == 0


def test_unaligned_open_start_returns_400_and_keeps_row(app, db_path):
    seed_equipment(db_path)
    admin = admin_client(app, db_path)

    resp = post_window(admin, "E1", "09:15", "12:00")
    open_start_after = equipment_row(db_path)["open_start"]

    assert resp.status_code == 400 and open_start_after == "09:00"


def test_open_start_not_before_open_end_returns_400_and_keeps_row(app, db_path):
    seed_equipment(db_path)
    admin = admin_client(app, db_path)

    resp = post_window(admin, "E1", "18:00", "09:00")
    row = equipment_row(db_path)

    assert resp.status_code == 400 and (row["open_start"], row["open_end"]) == ("09:00", "12:00")


def test_logged_in_student_sees_equipments_and_anonymous_is_rejected(app, db_path):
    name = "扫描电镜"
    seed_equipment(db_path, name=name, open_start="09:00", open_end="12:00")
    authed = login_student(app)
    anon = app.test_client()

    authed_resp = authed.get("/equipments")
    anon_resp = anon.get("/equipments")

    assert (authed_resp.status_code, anon_resp.status_code) == (200, 401) and all(
        value in authed_resp.get_data(as_text=True) for value in (name, "09:00", "12:00")
    )


def test_open_window_excludes_local_0730_and_2200():
    from src.app.slot_service import build_grid
    from src.core.timeutil import utc_to_local

    local_times = {
        utc_to_local(slot).strftime("%H:%M") for slot in build_grid("08:00", "22:00", DAY)
    }

    assert "07:30" not in local_times and "22:00" not in local_times and min(local_times) == "08:00"


def test_admin_creates_equipment_with_default_window_and_audit(app, db_path):
    admin = admin_client(app, db_path)

    resp = admin.post(
        "/admin/equipments",
        data={"name": "离心机", "csrf_token": csrf_cookie(admin)},
    )
    conn = connect(db_path)
    try:
        row = conn.execute("SELECT * FROM equipment WHERE name = '离心机'").fetchone()
        audit_count = conn.execute(
            "SELECT COUNT(*) AS n FROM audit_log WHERE action = 'equipment_update'"
            " AND target_type = 'equipment'"
        ).fetchone()["n"]
    finally:
        conn.close()

    assert resp.status_code == 303 and (row["open_start"], row["open_end"]) == ("08:00", "22:00")
    assert audit_count == 1


def test_admin_equipments_page_has_admin_link_and_editable_name(app, db_path):
    seed_equipment(db_path, name="显微镜")
    admin = admin_client(app, db_path)

    catalog = admin.get("/equipments")
    maintenance = admin.get("/admin/equipments")

    assert catalog.status_code == 200 and "/admin/equipments" in catalog.get_data(as_text=True)
    body = maintenance.get_data(as_text=True)
    assert maintenance.status_code == 200
    assert re.search(r'<input type="text" name="name" value="显微镜"', body) is not None


def test_student_dashboard_does_not_show_admin_link(app):
    student = login_student(app)

    body = student.get("/equipments").get_data(as_text=True)

    assert "/admin/equipments" not in body


def test_failed_window_save_rerenders_admin_page_with_context(app, db_path):
    seed_equipment(db_path, name="显微镜")
    admin = admin_client(app, db_path)

    resp = post_window(admin, "E1", "09:15", "12:00")
    body = resp.get_data(as_text=True)

    assert resp.status_code == 400
    assert 'action="/admin/equipments/E1/window"' in body and "显微镜" in body


def test_window_narrowing_ignores_past_occupancy(app, db_path):
    seed_equipment(db_path, open_start="09:00", open_end="12:00")
    seed_raw_occupancy(db_path, "2020-01-01T00:00:00Z")
    admin = admin_client(app, db_path)

    resp = post_window(admin, "E1", "09:00", "12:00")

    assert resp.status_code == 303


def test_student_cannot_manage_equipments(app, db_path):
    seed_equipment(db_path)
    student = login_student(app)

    responses = [
        student.get("/admin/equipments"),
        student.post("/admin/equipments", data={"name": "越权设备", "csrf_token": csrf_cookie(student)}),
        student.post(
            "/admin/equipments/E1/window",
            data={"open_start": "09:00", "open_end": "13:00", "csrf_token": csrf_cookie(student)},
        ),
    ]

    assert [resp.status_code for resp in responses] == [403, 403, 403]


def test_anonymous_cannot_manage_equipments(app):
    client = app.test_client()

    assert client.get("/admin/equipments").status_code == 401


def test_admin_equipment_writes_require_csrf(app, db_path):
    seed_equipment(db_path)
    admin = admin_client(app, db_path)

    create = admin.post("/admin/equipments", data={"name": "无 token 设备"})
    update = admin.post(
        "/admin/equipments/E1/window", data={"open_start": "09:00", "open_end": "13:00"}
    )

    assert (create.status_code, update.status_code) == (400, 400)


def test_successful_window_update_persists_and_audits(app, db_path):
    seed_equipment(db_path)
    admin = admin_client(app, db_path)

    resp = post_window(admin, "E1", "09:00", "13:00")
    row = equipment_row(db_path)

    assert resp.status_code == 303 and "/admin/equipments" in resp.headers["Location"]
    assert row["open_end"] == "13:00" and audit_count(db_path) == 1


def test_create_equipment_with_explicit_window(app, db_path):
    admin = admin_client(app, db_path)

    resp = admin.post(
        "/admin/equipments",
        data={
            "name": "分光计",
            "open_start": "09:00",
            "open_end": "12:00",
            "csrf_token": csrf_cookie(admin),
        },
    )
    conn = connect(db_path)
    try:
        row = conn.execute("SELECT * FROM equipment WHERE name = '分光计'").fetchone()
    finally:
        conn.close()

    assert resp.status_code == 303 and (row["open_start"], row["open_end"]) == ("09:00", "12:00")


def test_create_equipment_rejects_invalid_window(app, db_path):
    admin = admin_client(app, db_path)

    resp = admin.post(
        "/admin/equipments",
        data={
            "name": "坏窗口设备",
            "open_start": "09:15",
            "open_end": "12:00",
            "csrf_token": csrf_cookie(admin),
        },
    )
    conn = connect(db_path)
    try:
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM equipment WHERE name = '坏窗口设备'"
        ).fetchone()["n"]
    finally:
        conn.close()

    assert resp.status_code == 400 and count == 0


def test_window_update_missing_equipment_returns_404(app, db_path):
    admin = admin_client(app, db_path)

    resp = post_window(admin, "MISSING", "09:00", "12:00")

    assert resp.status_code == 404
