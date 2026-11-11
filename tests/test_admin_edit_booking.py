"""Story 3.2 验收测试：管理员改单。

行为经公开入口（`GET/POST /admin/bookings/<id>/edit`、`GET /admin/week` 与
`GET /slots`）观察；用户、设备与预约直接 INSERT 播种，落库断言用只读 SQL。
换设备按 D-011 拒绝：改单只改时段，设备不同返回 400。
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
NOW = "2026-11-09T00:00:00Z"  # 本地周一 08:00
WEEK = "2026-11-09"
DAY = "2026-11-11"
NEXT_DAY = "2026-11-12"
ADMIN_ID = "a" * 32
STUDENT_A = "b" * 32
STUDENT_B = "c" * 32
STUDENT_C = "d" * 32
BOOKING_ID = "1" * 32
OTHER_BOOKING_ID = "2" * 32
CSRF_PATTERN = re.compile(r'name="csrf_token" value="([^"]+)"')
STATE_PATTERN = re.compile(r'data-state="([^"]+)" data-slot="([^"]+)"')
CHECKBOX_PATTERN = re.compile(r'<input type="checkbox" name="slot" value="([^"]+)"')
CHECKED_PATTERN = re.compile(r'<input type="checkbox" name="slot" value="([^"]+)"[^>]*\bchecked\b')


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
            (user_id, student_no, role, PASSWORD_HASH, "2026-11-09T00:00:00Z"),
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


def seed_booking(
    db_path,
    *,
    booking_id,
    owner_id,
    times,
    equipment_id="E1",
    day=DAY,
):
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO booking (id, owner_id, equipment_id, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (booking_id, owner_id, equipment_id, "2026-11-09T00:00:00Z", "2026-11-09T00:00:00Z"),
        )
        conn.executemany(
            "INSERT INTO occupancy (equipment_id, slot_start, kind, booking_id, created_at)"
            " VALUES (?, ?, \'booking\', ?, ?)",
            [(equipment_id, utc_at(day, hhmm), booking_id, "2026-11-09T00:00:00Z") for hhmm in times],
        )
        conn.commit()
    finally:
        conn.close()


def seed_lock(db_path, slot_start, equipment_id="E1"):
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO occupancy (equipment_id, slot_start, kind, booking_id, created_at)"
            " VALUES (?, ?, \'lock\', NULL, ?)",
            (equipment_id, slot_start, "2026-11-09T00:00:00Z"),
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


def student_client(app, user_id):
    client = app.test_client()
    login_as(client, user_id)
    return client


def occ_rows(db_path, booking_id=None):
    sql = "SELECT equipment_id, slot_start, kind, booking_id FROM occupancy"
    params = ()
    if booking_id is not None:
        sql += " WHERE booking_id = ?"
        params = (booking_id,)
    sql += " ORDER BY equipment_id, slot_start, kind, booking_id"
    return [tuple(row) for row in fetch(db_path, sql, params)]


def booking_row(db_path, booking_id=BOOKING_ID):
    return fetch(db_path, "SELECT * FROM booking WHERE id = ?", (booking_id,))[0]


def n_occ_for(db_path, booking_id=BOOKING_ID):
    return fetch(
        db_path, "SELECT COUNT(*) AS n FROM occupancy WHERE booking_id = ?", (booking_id,)
    )[0]["n"]


def duplicate_keys(db_path):
    return fetch(
        db_path,
        "SELECT equipment_id, slot_start, COUNT(*) AS duplicated FROM occupancy"
        " GROUP BY equipment_id, slot_start HAVING duplicated > 1",
    )


def audit_rows(db_path, action="booking_edit"):
    return fetch(db_path, "SELECT * FROM audit_log WHERE action = ? ORDER BY id", (action,))


def edit_url(booking_id=BOOKING_ID, **params):
    url = f"/admin/bookings/{booking_id}/edit"
    if params:
        from urllib.parse import urlencode

        url += "?" + urlencode(params)
    return url


def csrf_from_edit_page(client, booking_id=BOOKING_ID, **params):
    page = client.get(edit_url(booking_id, **params))
    assert page.status_code == 200
    match = CSRF_PATTERN.search(page.get_data(as_text=True))
    assert match is not None, "改单页未渲染 csrf_token"
    return match.group(1)


def post_edit(
    client,
    *,
    booking_id=BOOKING_ID,
    slots,
    equipment_id="E1",
    day=DAY,
    token="",
):
    data = {
        "equipment_id": equipment_id,
        "date": day,
        "slot": list(slots),
    }
    if token:
        data["csrf_token"] = token
    return client.post(edit_url(booking_id), data=data)


def cell_tag(html, slot_start):
    match = re.search(
        r"<li\b[^>]*data-slot=\"" + re.escape(slot_start) + r"\"[^>]*>",
        html,
    )
    assert match is not None, f"页面缺少 {slot_start} 的格子"
    return match.group(0)


def grid_states(client, day=DAY, equipment_id="E1"):
    page = client.get(f"/slots?equipment_id={equipment_id}&date={day}")
    assert page.status_code == 200
    return {slot: state for state, slot in STATE_PATTERN.findall(page.get_data(as_text=True))}


def test_conflict_returns_409_and_keeps_booking_rows_and_id(app, db_path, clock):
    seed_equipment(db_path)
    seed_user(db_path, STUDENT_A, "2025001")
    seed_user(db_path, STUDENT_B, "2025002")
    seed_booking(db_path, booking_id=BOOKING_ID, owner_id=STUDENT_A, times=["14:00", "14:30"])
    seed_booking(db_path, booking_id=OTHER_BOOKING_ID, owner_id=STUDENT_B, times=["15:00"])
    client = admin_client(app, db_path)
    before = occ_rows(db_path, BOOKING_ID)
    token = csrf_from_edit_page(client)

    resp = post_edit(client, slots=[utc_at(DAY, "14:30"), utc_at(DAY, "15:00")], token=token)
    after = occ_rows(db_path, BOOKING_ID)

    assert resp.status_code == 409
    assert sorted(before) == sorted(after)
    assert booking_row(db_path)["id"] == BOOKING_ID
    assert audit_rows(db_path) == []


def test_conflict_marks_cell_and_keeps_submitted_day_and_selection(app, db_path, clock):
    seed_equipment(db_path)
    seed_user(db_path, STUDENT_A, "2025001")
    seed_user(db_path, STUDENT_B, "2025002")
    seed_booking(db_path, booking_id=BOOKING_ID, owner_id=STUDENT_A, times=["14:00"])
    seed_booking(
        db_path,
        booking_id=OTHER_BOOKING_ID,
        owner_id=STUDENT_B,
        times=["15:00"],
        day=NEXT_DAY,
    )
    client = admin_client(app, db_path)
    before = occ_rows(db_path)
    token = csrf_from_edit_page(client)
    submitted_slots = [utc_at(NEXT_DAY, "14:30"), utc_at(NEXT_DAY, "15:00")]

    resp = post_edit(
        client,
        slots=submitted_slots,
        day=NEXT_DAY,
        token=token,
    )
    html = resp.get_data(as_text=True)

    assert resp.status_code == 409
    assert f'data-grid-day="{NEXT_DAY}"' in html
    assert f'name="date" value="{NEXT_DAY}"' in html
    assert submitted_slots[0] in CHECKED_PATTERN.findall(html)
    assert 'data-conflict="1"' in cell_tag(html, submitted_slots[1])
    assert occ_rows(db_path) == before


def test_successful_edit_returns_303_to_original_week_and_writes_one_audit(app, db_path, clock):
    seed_equipment(db_path)
    seed_user(db_path, STUDENT_A, "2025001")
    old_slots = [utc_at(DAY, "14:00"), utc_at(DAY, "14:30")]
    new_slots = [utc_at(DAY, "16:00"), utc_at(DAY, "16:30")]
    seed_booking(db_path, booking_id=BOOKING_ID, owner_id=STUDENT_A, times=["14:00", "14:30"])
    client = admin_client(app, db_path)
    token = csrf_from_edit_page(client)

    resp = post_edit(client, slots=new_slots, token=token)
    rows = audit_rows(db_path)

    assert resp.status_code == 303
    assert resp.headers["Location"] == f"/admin/week?week={WEEK}"
    assert len(rows) == 1
    row = rows[0]
    assert (row["actor_id"], row["action"], row["target_type"]) == (
        ADMIN_ID,
        "booking_edit",
        "booking",
    )
    assert row["target_id"] == BOOKING_ID
    assert json.loads(row["before_json"])["slots"] == sorted(old_slots)
    assert json.loads(row["after_json"])["slots"] == sorted(new_slots)
    assert booking_row(db_path)["id"] == BOOKING_ID


def test_successful_edit_leaves_no_duplicate_keys_and_exact_row_count(app, db_path, clock):
    seed_equipment(db_path)
    seed_user(db_path, STUDENT_A, "2025001")
    new_slots = [utc_at(DAY, "16:00"), utc_at(DAY, "16:30"), utc_at(DAY, "17:00")]
    seed_booking(db_path, booking_id=BOOKING_ID, owner_id=STUDENT_A, times=["14:00"])
    client = admin_client(app, db_path)
    token = csrf_from_edit_page(client)

    assert post_edit(client, slots=new_slots, token=token).status_code == 303

    assert duplicate_keys(db_path) == []
    assert n_occ_for(db_path) == len(new_slots)


def test_moved_slot_is_free_and_target_is_booked_for_another_student(app, db_path, clock):
    seed_equipment(db_path)
    seed_user(db_path, STUDENT_A, "2025001")
    old_slot = utc_at(DAY, "14:00")
    new_slot = utc_at(DAY, "16:00")
    seed_booking(db_path, booking_id=BOOKING_ID, owner_id=STUDENT_A, times=["14:00"])
    client = admin_client(app, db_path)
    token = csrf_from_edit_page(client)
    assert post_edit(client, slots=[new_slot], token=token).status_code == 303

    seed_user(db_path, STUDENT_C, "2025003")
    other_student = student_client(app, STUDENT_C)
    grid = grid_states(other_student)

    assert (grid[old_slot], grid[new_slot]) == ("free", "booked_by_other")


def test_student_post_returns_403_and_changes_nothing(app, db_path, clock):
    seed_equipment(db_path)
    seed_user(db_path, STUDENT_A, "2025001")
    seed_booking(db_path, booking_id=BOOKING_ID, owner_id=STUDENT_A, times=["14:00"])
    student = student_client(app, STUDENT_A)
    before = occ_rows(db_path)

    resp = post_edit(student, slots=[utc_at(DAY, "16:00")])

    assert resp.status_code == 403
    assert occ_rows(db_path) == before
    assert audit_rows(db_path) == []


def test_equipment_change_returns_400_not_404_or_409(app, db_path, clock):
    seed_equipment(db_path, "E1")
    seed_equipment(db_path, "E2")
    seed_user(db_path, STUDENT_A, "2025001")
    seed_booking(db_path, booking_id=BOOKING_ID, owner_id=STUDENT_A, times=["14:00"])
    client = admin_client(app, db_path)
    before = occ_rows(db_path)
    token = csrf_from_edit_page(client)

    resp = post_edit(
        client,
        slots=[utc_at(DAY, "16:00")],
        equipment_id="E2",
        token=token,
    )

    assert resp.status_code == 400
    assert occ_rows(db_path) == before
    assert booking_row(db_path)["equipment_id"] == "E1"
    assert audit_rows(db_path) == []


def test_edit_form_preselects_current_slots_and_fixed_equipment(app, db_path, clock):
    seed_equipment(db_path)
    seed_user(db_path, STUDENT_A, "2025001")
    current = [utc_at(DAY, "14:00"), utc_at(DAY, "14:30")]
    seed_booking(db_path, booking_id=BOOKING_ID, owner_id=STUDENT_A, times=["14:00", "14:30"])
    client = admin_client(app, db_path)

    resp = client.get(edit_url())
    html = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert BOOKING_ID in html
    assert 'name="equipment_id" value="E1"' in html
    assert f'name="date" value="{DAY}"' in html
    assert "11-11 14:00" in html and "11-11 14:30" in html
    assert set(current) <= set(CHECKBOX_PATTERN.findall(html))
    assert all('data-selected="1"' in cell_tag(html, slot) for slot in current)


def test_week_view_links_to_edit_form_for_each_booking(app, db_path, clock):
    seed_equipment(db_path)
    seed_user(db_path, STUDENT_A, "2025001")
    seed_booking(db_path, booking_id=BOOKING_ID, owner_id=STUDENT_A, times=["14:00"])
    client = admin_client(app, db_path)

    html = client.get(f"/admin/week?week={WEEK}").get_data(as_text=True)

    assert f"/admin/bookings/{BOOKING_ID}/edit" in html


def test_anonymous_gets_401_and_student_gets_403_on_edit_page(app, db_path, clock):
    seed_equipment(db_path)
    seed_user(db_path, STUDENT_A, "2025001")
    seed_booking(db_path, booking_id=BOOKING_ID, owner_id=STUDENT_A, times=["14:00"])
    student = student_client(app, STUDENT_A)

    anonymous = app.test_client().get(edit_url())
    anonymous_post = app.test_client().post(
        edit_url(), data={"equipment_id": "E1", "date": DAY, "slot": [utc_at(DAY, "16:00")]}
    )
    student_get = student.get(edit_url())

    assert (anonymous.status_code, student_get.status_code) == (401, 403)
    assert anonymous_post.status_code == 401


def test_unknown_booking_returns_404_on_get_and_post(app, db_path, clock):
    seed_equipment(db_path)
    seed_user(db_path, STUDENT_A, "2025001")
    seed_booking(db_path, booking_id=BOOKING_ID, owner_id=STUDENT_A, times=["14:00"])
    client = admin_client(app, db_path)
    token = csrf_from_edit_page(client)

    missing_get = client.get(edit_url("9" * 32))
    missing_post = post_edit(
        client,
        booking_id="9" * 32,
        slots=[utc_at(DAY, "16:00")],
        token=token,
    )

    assert (missing_get.status_code, missing_post.status_code) == (404, 404)


def test_missing_csrf_returns_400_and_changes_nothing(app, db_path, clock):
    seed_equipment(db_path)
    seed_user(db_path, STUDENT_A, "2025001")
    seed_booking(db_path, booking_id=BOOKING_ID, owner_id=STUDENT_A, times=["14:00"])
    client = admin_client(app, db_path)
    before = occ_rows(db_path)

    resp = post_edit(client, slots=[utc_at(DAY, "16:00")])

    assert resp.status_code == 400
    assert occ_rows(db_path) == before
    assert audit_rows(db_path) == []


def test_bad_date_falls_back_to_original_day_with_400(app, db_path, clock):
    seed_equipment(db_path)
    seed_user(db_path, STUDENT_A, "2025001")
    seed_booking(db_path, booking_id=BOOKING_ID, owner_id=STUDENT_A, times=["14:00"])
    client = admin_client(app, db_path)

    resp = client.get(edit_url(date="not-a-date"))
    html = resp.get_data(as_text=True)

    assert resp.status_code == 400
    assert f'name="date" value="{DAY}"' in html


def test_locked_target_returns_409_and_marks_locked_cell(app, db_path, clock):
    seed_equipment(db_path)
    seed_user(db_path, STUDENT_A, "2025001")
    seed_booking(db_path, booking_id=BOOKING_ID, owner_id=STUDENT_A, times=["14:00"])
    locked_slot = utc_at(DAY, "15:00")
    seed_lock(db_path, locked_slot)
    client = admin_client(app, db_path)
    before = occ_rows(db_path)
    token = csrf_from_edit_page(client)

    resp = post_edit(client, slots=[utc_at(DAY, "14:30"), locked_slot], token=token)
    html = resp.get_data(as_text=True)

    assert resp.status_code == 409
    assert locked_slot in html
    assert 'data-state="locked"' in cell_tag(html, locked_slot)
    assert 'data-conflict="1"' in cell_tag(html, locked_slot)
    assert occ_rows(db_path) == before
    assert audit_rows(db_path) == []


def test_conflict_body_lists_every_conflicting_slot(app, db_path, clock):
    seed_equipment(db_path)
    seed_user(db_path, STUDENT_A, "2025001")
    seed_user(db_path, STUDENT_B, "2025002")
    seed_booking(db_path, booking_id=BOOKING_ID, owner_id=STUDENT_A, times=["14:00"])
    seed_booking(db_path, booking_id=OTHER_BOOKING_ID, owner_id=STUDENT_B, times=["15:00"])
    locked_slot = utc_at(DAY, "15:30")
    seed_lock(db_path, locked_slot)
    client = admin_client(app, db_path)
    token = csrf_from_edit_page(client)

    resp = post_edit(
        client,
        slots=[utc_at(DAY, "14:30"), utc_at(DAY, "15:00"), locked_slot],
        token=token,
    )
    html = resp.get_data(as_text=True)

    assert resp.status_code == 409
    assert utc_at(DAY, "15:00") in html and locked_slot in html
    assert 'data-conflict="1"' in cell_tag(html, utc_at(DAY, "15:00"))
    assert 'data-conflict="1"' in cell_tag(html, locked_slot)


def test_edit_get_writes_nothing(app, db_path, clock):
    seed_equipment(db_path)
    seed_user(db_path, STUDENT_A, "2025001")
    seed_booking(db_path, booking_id=BOOKING_ID, owner_id=STUDENT_A, times=["14:00"])
    client = admin_client(app, db_path)
    before_occ = occ_rows(db_path)
    before_booking = tuple(booking_row(db_path))
    before_audit = len(audit_rows(db_path))

    assert client.get(edit_url()).status_code == 200

    assert occ_rows(db_path) == before_occ
    assert tuple(booking_row(db_path)) == before_booking
    assert len(audit_rows(db_path)) == before_audit


def test_conflict_off_submitted_grid_renders_page_scope_banner(app, db_path, clock):
    seed_equipment(db_path)
    seed_user(db_path, STUDENT_A, "2025001")
    seed_user(db_path, STUDENT_B, "2025002")
    seed_booking(db_path, booking_id=BOOKING_ID, owner_id=STUDENT_A, times=["14:00"])
    seed_booking(
        db_path,
        booking_id=OTHER_BOOKING_ID,
        owner_id=STUDENT_B,
        times=["15:00"],
        day=NEXT_DAY,
    )
    client = admin_client(app, db_path)
    token = csrf_from_edit_page(client)

    resp = post_edit(
        client,
        slots=[utc_at(NEXT_DAY, "14:30"), utc_at(NEXT_DAY, "15:00")],
        day=DAY,
        token=token,
    )
    html = resp.get_data(as_text=True)

    assert resp.status_code == 409
    assert 'data-conflict-page="1"' in html


def test_shifted_window_overlapping_old_rows_succeeds_via_http(app, db_path, clock):
    seed_equipment(db_path)
    seed_user(db_path, STUDENT_A, "2025001")
    new_slots = [utc_at(DAY, "14:30"), utc_at(DAY, "15:00")]
    seed_booking(db_path, booking_id=BOOKING_ID, owner_id=STUDENT_A, times=["14:00", "14:30"])
    client = admin_client(app, db_path)
    token = csrf_from_edit_page(client)

    resp = post_edit(client, slots=new_slots, token=token)

    assert resp.status_code == 303
    assert [row[1] for row in occ_rows(db_path, BOOKING_ID)] == sorted(new_slots)
    assert duplicate_keys(db_path) == []
