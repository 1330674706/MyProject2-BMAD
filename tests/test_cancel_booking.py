"""Story 2.3 验收测试：我的预约与取消。

每条 AC 逐条对应 `_bmad-output/planning-artifacts/epics.md` 的 Story 2.3；
行为经公开入口（`GET /bookings/mine`、`POST /bookings/<id>/cancel` 与
`GET /slots`）触发，落库结果用只读 SQL 断言，设备数据直接 INSERT 播种。
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta

import pytest

from src.core.timeutil import local_to_utc

PLAINTEXT = "P@ssw0rd-lab"
CSRF_PATTERN = re.compile(r'name="csrf_token" value="([^"]+)"')
BOOKING_ID_PATTERN = re.compile(r'data-booking-id="([^"]+)"')
STATE_PATTERN = re.compile(r'data-state="([^"]+)" data-slot="([^"]+)"')

# 本地 12:30 的首个 slot 对应 UTC 04:30。
# NOW_121 = 04:30 - 2h01m；NOW_119 = 04:30 - 1h59m。
NOW_121 = "2030-01-01T02:29:00Z"
NOW_119 = "2030-01-01T02:31:00Z"
NOW_EXACT = "2030-01-01T02:30:00Z"
DAY = "2030-01-01"


@pytest.fixture
def clock(monkeypatch):
    state = {"now": NOW_121}

    def fixed_now():
        return state["now"]

    from src.app import booking_service, slot_service

    monkeypatch.setattr(booking_service, "now_utc", fixed_now)
    monkeypatch.setattr(slot_service, "now_utc", fixed_now)
    return state


def csrf_token(client, path):
    body = client.get(path).get_data(as_text=True)
    match = CSRF_PATTERN.search(body)
    assert match is not None, f"{path} 未渲染 csrf_token"
    return match.group(1)


def csrf_cookie(client):
    cookie = client.get_cookie("csrf")
    assert cookie is not None, "缺少 csrf cookie"
    return cookie.value


def register(client, student_no="2025001", password=PLAINTEXT):
    token = csrf_token(client, "/register")
    return client.post(
        "/register",
        data={"student_no": student_no, "password": password, "csrf_token": token},
    )


def login(client, student_no="2025001", password=PLAINTEXT):
    token = csrf_token(client, "/login")
    return client.post(
        "/login",
        data={"student_no": student_no, "password": password, "csrf_token": token},
    )


def login_student(app, student_no="2025001"):
    client = app.test_client()
    assert register(client, student_no=student_no).status_code == 303
    assert login(client, student_no=student_no).status_code == 303
    return client


def connect(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


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


def fetch(db_path, sql, params=()):
    conn = connect(db_path)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def local_slots(day, start_hhmm, count):
    hour, minute = (int(part) for part in start_hhmm.split(":"))
    start = datetime.fromisoformat(f"{day}T00:00:00") + timedelta(hours=hour, minutes=minute)
    return [local_to_utc(start + timedelta(minutes=30 * index)) for index in range(count)]


def post_booking(client, *, slots, equipment_id="E1", day=DAY, csrf=True):
    data = {"equipment_id": equipment_id, "date": day, "slot": list(slots)}
    if csrf:
        data["csrf_token"] = csrf_cookie(client)
    return client.post("/bookings", data=data)


def post_cancel(client, booking_id, *, csrf=True):
    data = {}
    if csrf:
        data["csrf_token"] = csrf_cookie(client)
    return client.post(f"/bookings/{booking_id}/cancel", data=data)


def booking_ids_for(db_path, student_no):
    rows = fetch(
        db_path,
        "SELECT b.id FROM booking AS b JOIN user AS u ON u.id = b.owner_id"
        " WHERE u.student_no = ? ORDER BY b.rowid",
        (student_no,),
    )
    return [row["id"] for row in rows]


def n_booking_for(db_path, booking_id):
    return fetch(
        db_path, "SELECT COUNT(*) AS n FROM booking WHERE id = ?", (booking_id,)
    )[0]["n"]


def n_occ_for(db_path, booking_id):
    return fetch(
        db_path, "SELECT COUNT(*) AS n FROM occupancy WHERE booking_id = ?", (booking_id,)
    )[0]["n"]


def audit_cancel_count(db_path, booking_id):
    return fetch(
        db_path,
        "SELECT COUNT(*) AS n FROM audit_log WHERE target_id = ? AND action = 'booking_cancel'",
        (booking_id,),
    )[0]["n"]


def booking_rows(body):
    return {
        booking_id: html
        for booking_id, html in re.findall(
            r'<tr data-booking-id="([^"]+)">(.*?)</tr>', body, re.S
        )
    }


def grid_states(client, day=DAY, equipment_id="E1"):
    page = client.get(f"/slots?equipment_id={equipment_id}&date={day}")
    assert page.status_code == 200
    return {slot: state for state, slot in STATE_PATTERN.findall(page.get_data(as_text=True))}


def test_my_bookings_page_lists_only_the_current_students_bookings(app, db_path, clock):
    seed_equipment(db_path)
    student_a = login_student(app, "2025001")
    assert post_booking(student_a, slots=local_slots(DAY, "12:00", 1)).status_code == 303
    assert post_booking(student_a, slots=local_slots(DAY, "14:00", 2)).status_code == 303
    student_b = login_student(app, "2025002")
    assert post_booking(student_b, slots=local_slots(DAY, "16:00", 1)).status_code == 303

    a_booking_ids = booking_ids_for(db_path, "2025001")
    resp = student_a.get("/bookings/mine")
    body = resp.get_data(as_text=True)
    rendered_ids = set(BOOKING_ID_PATTERN.findall(body))
    rows = booking_rows(body)
    blocked_row = next(html for html in rows.values() if "01-01 12:00" in html)
    open_row = next(html for html in rows.values() if "01-01 14:00" in html)

    assert resp.status_code == 200
    assert rendered_ids == set(a_booking_ids)
    assert len(a_booking_ids) == 2
    assert "已过取消截止" in blocked_row and " disabled" in blocked_row
    assert "可取消" in open_row and " disabled" not in open_row
    assert "2030-01-01T04:00:00Z" not in body


def test_cancel_within_window_deletes_booking_and_its_occupancies(app, db_path, clock):
    seed_equipment(db_path)
    student_a = login_student(app)
    slots = local_slots(DAY, "12:30", 3)
    assert post_booking(student_a, slots=slots).status_code == 303
    booking_id = booking_ids_for(db_path, "2025001")[0]

    resp = post_cancel(student_a, booking_id)

    assert resp.status_code == 303
    assert n_booking_for(db_path, booking_id) == 0
    assert n_occ_for(db_path, booking_id) == 0
    assert audit_cancel_count(db_path, booking_id) == 1


def test_cancel_inside_two_hour_cutoff_returns_400_and_changes_nothing(app, db_path, clock):
    clock["now"] = NOW_119
    seed_equipment(db_path)
    student_a = login_student(app)
    slots = local_slots(DAY, "12:30", 3)
    assert post_booking(student_a, slots=slots).status_code == 303
    booking_id = booking_ids_for(db_path, "2025001")[0]

    resp = post_cancel(student_a, booking_id)

    assert resp.status_code == 400
    assert (n_booking_for(db_path, booking_id), n_occ_for(db_path, booking_id)) == (1, 3)
    assert audit_cancel_count(db_path, booking_id) == 0


def test_cancel_another_students_booking_returns_403_and_changes_nothing(app, db_path, clock):
    seed_equipment(db_path)
    student_a = login_student(app, "2025001")
    student_b = login_student(app, "2025002")
    slots = local_slots(DAY, "12:30", 3)
    assert post_booking(student_b, slots=slots).status_code == 303
    b_booking_id = booking_ids_for(db_path, "2025002")[0]

    resp = post_cancel(student_a, b_booking_id)

    assert resp.status_code == 403
    assert (n_booking_for(db_path, b_booking_id), n_occ_for(db_path, b_booking_id)) == (1, 3)
    assert audit_cancel_count(db_path, b_booking_id) == 0


def test_cancel_another_students_booking_inside_cutoff_is_403_not_400(app, db_path, clock):
    clock["now"] = NOW_119
    seed_equipment(db_path)
    student_a = login_student(app, "2025001")
    student_b = login_student(app, "2025002")
    slots = local_slots(DAY, "12:30", 3)
    assert post_booking(student_b, slots=slots).status_code == 303
    b_booking_id = booking_ids_for(db_path, "2025002")[0]

    resp = post_cancel(student_a, b_booking_id)

    assert resp.status_code == 403
    assert (n_booking_for(db_path, b_booking_id), n_occ_for(db_path, b_booking_id)) == (1, 3)
    assert audit_cancel_count(db_path, b_booking_id) == 0


def test_cancel_at_exactly_two_hours_is_allowed(app, db_path, clock):
    clock["now"] = NOW_EXACT
    seed_equipment(db_path)
    student_a = login_student(app)
    slots = local_slots(DAY, "12:30", 3)
    assert post_booking(student_a, slots=slots).status_code == 303
    booking_id = booking_ids_for(db_path, "2025001")[0]

    resp = post_cancel(student_a, booking_id)

    assert resp.status_code == 303
    assert (n_booking_for(db_path, booking_id), n_occ_for(db_path, booking_id)) == (0, 0)


def test_cancel_without_csrf_returns_400_and_changes_nothing(app, db_path, clock):
    seed_equipment(db_path)
    student_a = login_student(app)
    slots = local_slots(DAY, "12:30", 3)
    assert post_booking(student_a, slots=slots).status_code == 303
    booking_id = booking_ids_for(db_path, "2025001")[0]

    resp = post_cancel(student_a, booking_id, csrf=False)

    assert resp.status_code == 400
    assert (n_booking_for(db_path, booking_id), n_occ_for(db_path, booking_id)) == (1, 3)
    assert audit_cancel_count(db_path, booking_id) == 0


def test_freed_slots_are_bookable_by_anyone_including_the_owner(app, db_path, clock):
    seed_equipment(db_path)
    student_a = login_student(app, "2025001")
    slots = local_slots(DAY, "12:30", 3)
    assert post_booking(student_a, slots=slots).status_code == 303
    booking_id = booking_ids_for(db_path, "2025001")[0]
    assert post_cancel(student_a, booking_id).status_code == 303

    student_c = login_student(app, "2025003")
    states = grid_states(student_c)
    c_submit = post_booking(student_c, slots=[slots[1]])
    a_submit = post_booking(student_a, slots=[slots[2]])

    assert {states[slot] for slot in slots} == {"free"}
    assert (c_submit.status_code, a_submit.status_code) == (303, 303)


def test_second_cancel_returns_404_and_does_not_append_audit(app, db_path, clock):
    seed_equipment(db_path)
    student_a = login_student(app)
    slots = local_slots(DAY, "12:30", 3)
    assert post_booking(student_a, slots=slots).status_code == 303
    booking_id = booking_ids_for(db_path, "2025001")[0]
    assert post_cancel(student_a, booking_id).status_code == 303
    audit_before = fetch(
        db_path, "SELECT COUNT(*) AS n FROM audit_log WHERE target_id = ?", (booking_id,)
    )[0]["n"]

    second = post_cancel(student_a, booking_id)

    audit_after = fetch(
        db_path, "SELECT COUNT(*) AS n FROM audit_log WHERE target_id = ?", (booking_id,)
    )[0]["n"]
    assert second.status_code == 404
    assert audit_after == audit_before


def test_cancel_audit_records_sorted_slots_in_before_json(app, db_path, clock):
    seed_equipment(db_path)
    student_a = login_student(app)
    slots = local_slots(DAY, "12:30", 3)
    assert post_booking(student_a, slots=slots).status_code == 303
    booking_id = booking_ids_for(db_path, "2025001")[0]
    assert post_cancel(student_a, booking_id).status_code == 303

    row = fetch(
        db_path,
        "SELECT * FROM audit_log WHERE target_id = ? AND action = 'booking_cancel'"
        " ORDER BY id DESC LIMIT 1",
        (booking_id,),
    )[0]
    before = json.loads(row["before_json"])

    assert row["action"] == "booking_cancel"
    assert before["slots"] == sorted(slots)
    assert before["equipment_id"] == "E1"
    assert before["created_at"] == "2030-01-01T02:29:00Z"
    assert before["updated_at"] == before["created_at"]
    assert row["actor_id"] and row["target_type"] == "booking"
    assert row["after_json"] is None
