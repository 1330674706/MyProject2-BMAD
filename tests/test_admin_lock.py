"""Story 3.3 验收测试：管理员锁定与解锁 slot。

行为经公开入口（`GET /admin/equipments/<id>/lock`、`POST .../lock`、`POST .../unlock`、
`GET /slots`、`POST /bookings`）观察；用户、设备、预约与锁直接 INSERT 播种，
落库断言用只读 SQL。锁必须是与预约共用同一 `(equipment_id, slot_start)` 键空间的
`kind='lock'`、`booking_id IS NULL` 行。
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime

import pytest
from werkzeug.security import generate_password_hash

from src.core.timeutil import local_to_utc

PASSWORD_HASH = generate_password_hash("P@ssw0rd-lab")
NOW = "2026-11-11T00:00:00Z"  # 本地周三 08:00
DAY = "2026-11-11"
WEEK = "2026-11-09"
ADMIN_ID = "a" * 32
STUDENT_A = "b" * 32
BOOKING_ID = "1" * 32
CSRF_PATTERN = re.compile(r'name="csrf_token" value="([^"]+)"')
STATE_PATTERN = re.compile(r'data-state="([^"]+)" data-slot="([^"]+)"')
CHECKBOX_PATTERN = re.compile(r'<input type="checkbox" name="slot" value="([^"]+)"')


@pytest.fixture
def clock(monkeypatch):
    def fixed_now():
        return NOW

    from src.app import booking_service, slot_service

    monkeypatch.setattr(booking_service, "now_utc", fixed_now)
    monkeypatch.setattr(slot_service, "now_utc", fixed_now)


def connect(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def fetch(db_path, sql, params=()):
    conn = connect(db_path)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def seed_user(db_path, user_id, student_no, role="student"):
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO user (id, student_no, role, password_hash, password_version, active, created_at)"
            " VALUES (?, ?, ?, ?, 1, 1, ?)",
            (user_id, student_no, role, PASSWORD_HASH, "2026-11-11T00:00:00Z"),
        )
        conn.commit()
    finally:
        conn.close()


def seed_equipment(db_path, equipment_id="E1", open_start="08:00", open_end="22:00"):
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO equipment (id, name, open_start, open_end, active) VALUES (?, ?, ?, ?, 1)",
            (equipment_id, f"设备{equipment_id}", open_start, open_end),
        )
        conn.commit()
    finally:
        conn.close()


def utc_at(day, hhmm):
    return local_to_utc(datetime.fromisoformat(f"{day}T{hhmm}:00"))


def seed_booking(db_path, *, booking_id=BOOKING_ID, owner_id, times, equipment_id="E1", day=DAY):
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO booking (id, owner_id, equipment_id, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (booking_id, owner_id, equipment_id, NOW, NOW),
        )
        conn.executemany(
            "INSERT INTO occupancy (equipment_id, slot_start, kind, booking_id, created_at)"
            " VALUES (?, ?, \'booking\', ?, ?)",
            [(equipment_id, utc_at(day, hhmm), booking_id, NOW) for hhmm in times],
        )
        conn.commit()
    finally:
        conn.close()


def seed_lock(db_path, hhmm, equipment_id="E1", day=DAY):
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO occupancy (equipment_id, slot_start, kind, booking_id, created_at)"
            " VALUES (?, ?, \'lock\', NULL, ?)",
            (equipment_id, utc_at(day, hhmm), NOW),
        )
        conn.commit()
    finally:
        conn.close()


def login_as(client, user_id, role="student", password_version=1):
    with client.session_transaction() as session:
        session["uid"] = user_id
        session["role"] = role
        session["pv"] = password_version


def admin_client(app, db_path):
    seed_user(db_path, ADMIN_ID, "A0001", role="admin")
    client = app.test_client()
    login_as(client, ADMIN_ID, role="admin")
    return client


def student_client(app, db_path, user_id=STUDENT_A, student_no="2025001"):
    seed_user(db_path, user_id, student_no)
    client = app.test_client()
    login_as(client, user_id)
    return client


def occ_at(db_path, hhmm, equipment_id="E1", day=DAY):
    return [
        tuple(row)
        for row in fetch(
            db_path,
            "SELECT equipment_id, slot_start, kind, booking_id FROM occupancy"
            " WHERE equipment_id = ? AND slot_start = ?",
            (equipment_id, utc_at(day, hhmm)),
        )
    ]


def lock_rows(db_path, equipment_id="E1"):
    return [
        tuple(row)
        for row in fetch(
            db_path,
            "SELECT equipment_id, slot_start, kind, booking_id FROM occupancy"
            " WHERE equipment_id = ? AND kind = \'lock\' ORDER BY slot_start",
            (equipment_id,),
        )
    ]


def n_occ_for(db_path, booking_id=BOOKING_ID):
    return fetch(
        db_path, "SELECT COUNT(*) AS n FROM occupancy WHERE booking_id = ?", (booking_id,)
    )[0]["n"]


def audit_rows(db_path):
    return fetch(
        db_path,
        "SELECT action, target_type, target_id, after_json FROM audit_log ORDER BY id",
    )


def lock_url(equipment_id="E1", day=DAY):
    return f"/admin/equipments/{equipment_id}/lock?date={day}"


def csrf_from_lock_page(client, equipment_id="E1", day=DAY):
    page = client.get(lock_url(equipment_id, day))
    assert page.status_code == 200
    match = CSRF_PATTERN.search(page.get_data(as_text=True))
    assert match is not None, "锁定页未渲染 csrf_token"
    return match.group(1)


def csrf_from_slots_page(client, equipment_id="E1", day=DAY):
    page = client.get(f"/slots?equipment_id={equipment_id}&date={day}")
    assert page.status_code == 200
    match = CSRF_PATTERN.search(page.get_data(as_text=True))
    assert match is not None, "时段页未渲染 csrf_token"
    return match.group(1)


def post_lock(client, *, slots, token="", equipment_id="E1", day=DAY):
    data = {"date": day, "slot": list(slots)}
    if token:
        data["csrf_token"] = token
    return client.post(f"/admin/equipments/{equipment_id}/lock", data=data)


def post_unlock(client, *, slots, token="", equipment_id="E1", day=DAY):
    data = {"date": day, "slot": list(slots)}
    if token:
        data["csrf_token"] = token
    return client.post(f"/admin/equipments/{equipment_id}/unlock", data=data)


def post_booking(client, *, hhmm, token, equipment_id="E1", day=DAY):
    return client.post(
        "/bookings",
        data={
            "csrf_token": token,
            "equipment_id": equipment_id,
            "date": day,
            "slot": [utc_at(day, hhmm)],
        },
    )


def grid_states(client, equipment_id="E1", day=DAY):
    page = client.get(f"/slots?equipment_id={equipment_id}&date={day}")
    assert page.status_code == 200
    return {slot: state for state, slot in STATE_PATTERN.findall(page.get_data(as_text=True))}


def test_lock_free_slot_inserts_single_lock_row(app, db_path, clock):
    seed_equipment(db_path)
    client = admin_client(app, db_path)
    token = csrf_from_lock_page(client)

    resp = post_lock(client, slots=[utc_at(DAY, "10:00")], token=token)

    assert resp.status_code == 303
    assert resp.headers["Location"] == f"/admin/week?week={WEEK}"
    rows = occ_at(db_path, "10:00")
    assert len(rows) == 1
    assert rows[0][2] == "lock"
    assert rows[0][3] is None


def test_lock_redirects_to_the_week_of_written_slots(app, db_path, clock):
    seed_equipment(db_path)
    client = admin_client(app, db_path)
    token = csrf_from_lock_page(client)

    resp = post_lock(
        client,
        slots=[utc_at("2026-11-16", "10:00")],
        token=token,
        day=DAY,
    )

    assert resp.status_code == 303
    assert resp.headers["Location"] == "/admin/week?week=2026-11-16"
    assert len(lock_rows(db_path)) == 1


def test_student_view_shows_locked_and_submit_returns_409(app, db_path, clock):
    seed_equipment(db_path)
    seed_lock(db_path, "10:00")
    client = student_client(app, db_path)

    states = grid_states(client)
    assert states[utc_at(DAY, "10:00")] == "locked"
    before = len(occ_at(db_path, "10:00"))
    token = csrf_from_slots_page(client)

    resp = post_booking(client, hhmm="10:00", token=token)

    assert resp.status_code == 409
    assert len(occ_at(db_path, "10:00")) == before
    body = resp.get_data(as_text=True)
    assert "equipment_id=E1" in body
    assert utc_at(DAY, "10:00") in body


def test_lock_booked_slot_returns_409_and_keeps_booking(app, db_path, clock):
    seed_equipment(db_path)
    seed_user(db_path, STUDENT_A, "2025001")
    seed_booking(db_path, owner_id=STUDENT_A, times=["10:00"])
    client = admin_client(app, db_path)
    token = csrf_from_lock_page(client)

    resp = post_lock(client, slots=[utc_at(DAY, "10:00")], token=token)

    assert resp.status_code == 409
    assert n_occ_for(db_path) == 1
    assert occ_at(db_path, "10:00")[0][2] == "booking"
    assert lock_rows(db_path) == []
    assert [row["action"] for row in audit_rows(db_path)] == []
    body = resp.get_data(as_text=True)
    assert "equipment_id=E1" in body
    assert utc_at(DAY, "10:00") in body


def test_unlock_restores_free_and_student_can_book(app, db_path, clock):
    seed_equipment(db_path)
    seed_lock(db_path, "10:00")
    admin = admin_client(app, db_path)
    token = csrf_from_lock_page(admin)

    resp = post_unlock(admin, slots=[utc_at(DAY, "10:00")], token=token)

    assert resp.status_code == 303
    assert occ_at(db_path, "10:00") == []
    student = student_client(app, db_path)
    assert grid_states(student)[utc_at(DAY, "10:00")] == "free"
    student_token = csrf_from_slots_page(student)
    submit = post_booking(student, hhmm="10:00", token=student_token)
    assert submit.status_code == 303
    assert occ_at(db_path, "10:00")[0][2] == "booking"


def test_lock_and_unlock_write_audit_entries(app, db_path, clock):
    seed_equipment(db_path)
    client = admin_client(app, db_path)
    token = csrf_from_lock_page(client)
    slot = utc_at(DAY, "10:00")

    assert post_lock(client, slots=[slot], token=token).status_code == 303
    assert post_unlock(client, slots=[slot], token=token).status_code == 303

    rows = audit_rows(db_path)
    assert [(row["action"], row["target_type"]) for row in rows] == [
        ("lock", "equipment"),
        ("unlock", "equipment"),
    ]
    assert all(row["target_id"] == "E1" for row in rows)
    assert all(slot in json.loads(row["after_json"])["slots"] for row in rows)


def test_duplicate_lock_returns_409_and_keeps_single_row(app, db_path, clock):
    seed_equipment(db_path)
    seed_lock(db_path, "10:00")
    client = admin_client(app, db_path)
    token = csrf_from_lock_page(client)

    resp = post_lock(client, slots=[utc_at(DAY, "10:00")], token=token)

    assert resp.status_code == 409
    assert len(lock_rows(db_path)) == 1
    assert audit_rows(db_path) == []


def test_unlock_missing_lock_returns_404(app, db_path, clock):
    seed_equipment(db_path)
    client = admin_client(app, db_path)
    token = csrf_from_lock_page(client)

    resp = post_unlock(client, slots=[utc_at(DAY, "10:00")], token=token)

    assert resp.status_code == 404
    assert occ_at(db_path, "10:00") == []
    assert audit_rows(db_path) == []
    assert utc_at(DAY, "10:00") in resp.get_data(as_text=True)


def test_lock_conflict_rerender_disables_resubmitting_the_cell(app, db_path, clock):
    seed_equipment(db_path)
    seed_lock(db_path, "10:00")
    client = admin_client(app, db_path)
    token = csrf_from_lock_page(client)

    resp = post_lock(client, slots=[utc_at(DAY, "10:00")], token=token)

    assert resp.status_code == 409
    body = resp.get_data(as_text=True)
    assert 'data-conflict="1"' in body
    assert utc_at(DAY, "10:00") not in CHECKBOX_PATTERN.findall(body)


def test_lock_batch_with_one_booked_slot_writes_nothing(app, db_path, clock):
    seed_equipment(db_path)
    seed_user(db_path, STUDENT_A, "2025001")
    seed_booking(db_path, owner_id=STUDENT_A, times=["10:30"])
    client = admin_client(app, db_path)
    token = csrf_from_lock_page(client)

    resp = post_lock(
        client,
        slots=[utc_at(DAY, "10:00"), utc_at(DAY, "10:30")],
        token=token,
    )

    assert resp.status_code == 409
    assert lock_rows(db_path) == []
    assert occ_at(db_path, "10:00") == []
    assert audit_rows(db_path) == []


def test_unlock_does_not_delete_booking(app, db_path, clock):
    seed_equipment(db_path)
    seed_user(db_path, STUDENT_A, "2025001")
    seed_booking(db_path, owner_id=STUDENT_A, times=["10:00"])
    client = admin_client(app, db_path)
    token = csrf_from_lock_page(client)

    resp = post_unlock(client, slots=[utc_at(DAY, "10:00")], token=token)

    assert resp.status_code == 404
    assert n_occ_for(db_path) == 1
    assert occ_at(db_path, "10:00")[0][2] == "booking"
    assert audit_rows(db_path) == []


def test_lock_requires_admin_and_csrf(app, db_path, clock):
    seed_equipment(db_path)

    anonymous = app.test_client()
    assert post_lock(anonymous, slots=[utc_at(DAY, "10:00")]).status_code == 401

    student = student_client(app, db_path)
    assert post_lock(student, slots=[utc_at(DAY, "10:00")]).status_code == 403

    admin = admin_client(app, db_path)
    assert post_lock(admin, slots=[utc_at(DAY, "10:00")]).status_code == 400
    assert post_unlock(admin, slots=[utc_at(DAY, "10:00")]).status_code == 400

    assert lock_rows(db_path) == []
    assert audit_rows(db_path) == []


def test_lock_page_requires_admin(app, db_path, clock):
    seed_equipment(db_path)

    assert app.test_client().get(lock_url()).status_code == 401
    student = student_client(app, db_path)
    assert student.get(lock_url()).status_code == 403


def test_lock_rejects_bad_shape_and_past_slot(app, db_path, clock):
    seed_equipment(db_path)
    client = admin_client(app, db_path)
    token = csrf_from_lock_page(client)

    assert post_lock(client, slots=["not-a-slot"], token=token).status_code == 400
    assert post_lock(client, slots=[utc_at(DAY, "07:00")], token=token).status_code == 400
    assert post_lock(client, slots=[utc_at(DAY, "23:00")], token=token).status_code == 400
    assert (
        post_lock(client, slots=[utc_at("2026-11-19", "10:00")], token=token).status_code
        == 400
    )

    assert lock_rows(db_path) == []
    assert audit_rows(db_path) == []


def test_lock_page_offers_free_and_locked_cells_and_week_link(app, db_path, clock):
    seed_equipment(db_path)
    seed_user(db_path, STUDENT_A, "2025001")
    seed_lock(db_path, "11:00")
    seed_booking(db_path, owner_id=STUDENT_A, times=["12:00"])
    client = admin_client(app, db_path)

    page = client.get(lock_url())
    assert page.status_code == 200
    checkboxes = CHECKBOX_PATTERN.findall(page.get_data(as_text=True))
    assert utc_at(DAY, "10:00") in checkboxes
    assert utc_at(DAY, "11:00") in checkboxes
    assert utc_at(DAY, "12:00") not in checkboxes
    assert utc_at(DAY, "08:00") not in checkboxes

    week = client.get(f"/admin/week?week={WEEK}")
    assert week.status_code == 200
    assert f"/admin/equipments/E1/lock" in week.get_data(as_text=True)


def test_lock_multiple_slots_writes_all_and_audits_list(app, db_path, clock):
    seed_equipment(db_path)
    client = admin_client(app, db_path)
    token = csrf_from_lock_page(client)
    slots = [utc_at(DAY, "10:00"), utc_at(DAY, "10:30")]

    resp = post_lock(client, slots=slots, token=token)

    assert resp.status_code == 303
    assert len(lock_rows(db_path)) == 2
    assert json.loads(audit_rows(db_path)[0]["after_json"])["slots"] == slots


def test_unlock_partial_missing_is_atomic(app, db_path, clock):
    seed_equipment(db_path)
    seed_lock(db_path, "10:00")
    client = admin_client(app, db_path)
    token = csrf_from_lock_page(client)

    resp = post_unlock(
        client,
        slots=[utc_at(DAY, "10:00"), utc_at(DAY, "10:30")],
        token=token,
    )

    assert resp.status_code == 404
    assert len(lock_rows(db_path)) == 1
    assert audit_rows(db_path) == []
