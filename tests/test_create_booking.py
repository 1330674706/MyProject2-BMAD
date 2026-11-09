"""Story 2.1 验收测试：提交连续 slot 预约。

每条 AC 逐条对应 `_bmad-output/planning-artifacts/epics.md` 的 Story 2.1。
测试只通过公开入口（`POST /bookings` 与 `GET /slots`）观察行为。
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta

import pytest

from src.core.timeutil import local_to_utc

PLAINTEXT = "P@ssw0rd-lab"
CSRF_PATTERN = re.compile(r'name="csrf_token" value="([^"]+)"')
STATE_PATTERN = re.compile(r'data-state="([^"]+)" data-slot="([^"]+)"')
CHECKBOX_PATTERN = re.compile(r'<input type="checkbox" name="slot" value="([^"]+)"')

NOW = "2030-01-01T02:00:00Z"
DAY = "2030-01-02"
STARTED_DAY = "2030-01-01"

pytestmark = pytest.mark.usefixtures("clock")


@pytest.fixture
def clock(monkeypatch):
    def fixed_now():
        return NOW

    try:
        from src.app import booking_service, slot_service
    except ImportError:
        return
    monkeypatch.setattr(booking_service, "now_utc", fixed_now)
    monkeypatch.setattr(slot_service, "now_utc", fixed_now)


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


def login_student(app):
    client = app.test_client()
    assert register(client).status_code == 303
    assert login(client).status_code == 303
    return client


def connect(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
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


def n_booking(db_path):
    return fetch(db_path, "SELECT COUNT(*) AS n FROM booking")[0]["n"]


def n_occ(db_path):
    return fetch(db_path, "SELECT COUNT(*) AS n FROM occupancy")[0]["n"]


def occ_rows(db_path):
    return fetch(db_path, "SELECT booking_id, slot_start FROM occupancy ORDER BY slot_start")


def counts(db_path):
    return (n_booking(db_path), n_occ(db_path))


def slot_at(day, hhmm):
    return local_to_utc(datetime.fromisoformat(f"{day}T{hhmm}:00"))


def local_slots(day, start_hhmm, count):
    hour, minute = (int(part) for part in start_hhmm.split(":"))
    start = datetime.fromisoformat(f"{day}T00:00:00") + timedelta(hours=hour, minutes=minute)
    return [local_to_utc(start + timedelta(minutes=30 * index)) for index in range(count)]


def post_booking(client, *, slots, equipment_id="E1", day=DAY, csrf=True):
    data = {"equipment_id": equipment_id, "date": day, "slot": list(slots)}
    if csrf:
        data["csrf_token"] = csrf_cookie(client)
    return client.post("/bookings", data=data)


def test_eight_contiguous_slots_create_one_booking_and_eight_occupancies(app, db_path):
    seed_equipment(db_path)
    client = login_student(app)
    slots = local_slots(DAY, "14:00", 8)

    resp = post_booking(client, slots=slots)
    rows = occ_rows(db_path)

    assert resp.status_code == 303
    assert n_booking(db_path) == 1
    assert n_occ(db_path) == 8
    assert len({row["booking_id"] for row in rows}) == 1
    assert {row["slot_start"] for row in rows} == set(slots)


def test_nine_contiguous_slots_return_400_and_write_nothing(app, db_path):
    seed_equipment(db_path)
    client = login_student(app)
    before = counts(db_path)

    resp = post_booking(client, slots=local_slots(DAY, "14:00", 9))

    assert resp.status_code == 400 and counts(db_path) == before


def test_non_contiguous_slots_return_400_and_write_nothing(app, db_path):
    seed_equipment(db_path)
    client = login_student(app)
    before = counts(db_path)

    resp = post_booking(client, slots=[slot_at(DAY, "14:00"), slot_at(DAY, "15:00")])

    assert resp.status_code == 400 and counts(db_path) == before


def test_unaligned_slot_returns_400_and_writes_nothing(app, db_path):
    seed_equipment(db_path)
    client = login_student(app)
    before = counts(db_path)

    resp = post_booking(client, slots=[slot_at(DAY, "14:15")])

    assert resp.status_code == 400 and counts(db_path) == before


def test_started_first_slot_returns_400_and_writes_nothing(app, db_path):
    seed_equipment(db_path)
    client = login_student(app)
    before = counts(db_path)

    resp = post_booking(client, slots=[slot_at(STARTED_DAY, "09:30")])

    assert resp.status_code == 400 and counts(db_path) == before


def test_first_slot_must_be_within_seven_days(app, db_path):
    seed_equipment(db_path)
    client = login_student(app)

    far = post_booking(client, slots=[slot_at("2030-01-08", "10:30")])
    near = post_booking(client, slots=[slot_at("2030-01-08", "09:30")])

    assert (far.status_code, near.status_code) == (400, 303)


def test_equipment_mismatch_or_unknown_returns_400_and_writes_nothing(app, db_path):
    seed_equipment(db_path, "E1", "08:00", "22:00")
    seed_equipment(db_path, "E2", "10:00", "12:00")
    client = login_student(app)
    before = counts(db_path)

    mismatch = post_booking(client, equipment_id="E2", slots=local_slots(DAY, "14:00", 1))
    unknown = post_booking(client, equipment_id="NOPE", slots=local_slots(DAY, "14:00", 1))

    assert (mismatch.status_code, unknown.status_code) == (400, 400)
    assert counts(db_path) == before


def test_anonymous_is_401_and_missing_csrf_is_400_with_no_writes(app, db_path):
    seed_equipment(db_path)
    client = login_student(app)
    slots = local_slots(DAY, "14:00", 1)
    before = counts(db_path)

    anonymous = app.test_client().post(
        "/bookings",
        data={"equipment_id": "E1", "date": DAY, "slot": slots},
    )
    no_csrf = post_booking(client, slots=slots, csrf=False)

    assert (anonymous.status_code, no_csrf.status_code) == (401, 400)
    assert counts(db_path) == before


def test_successful_booking_shows_booked_by_self_in_slot_grid(app, db_path):
    seed_equipment(db_path)
    client = login_student(app)
    slots = local_slots(DAY, "14:00", 8)
    resp = post_booking(client, slots=slots)

    assert resp.status_code == 303
    assert resp.headers["Location"] == f"/slots?equipment_id=E1&date={DAY}"

    audits = fetch(db_path, "SELECT * FROM audit_log WHERE action = 'booking_create'")
    assert len(audits) == 1
    assert audits[0]["target_id"] == occ_rows(db_path)[0]["booking_id"]

    page = client.get(f"/slots?equipment_id=E1&date={DAY}")
    states = {slot: state for state, slot in STATE_PATTERN.findall(page.get_data(as_text=True))}

    assert page.status_code == 200
    assert {states[slot] for slot in slots} == {"booked_by_self"}


def test_empty_selection_returns_400_and_writes_nothing(app, db_path):
    seed_equipment(db_path)
    client = login_student(app)
    before = counts(db_path)

    resp = post_booking(client, slots=[])

    assert resp.status_code == 400 and counts(db_path) == before


def test_booking_form_offers_checkboxes_only_for_free_slots(app, db_path):
    seed_equipment(db_path)
    client = login_student(app)
    all_slots = set(local_slots(DAY, "08:00", 28))
    booked = local_slots(DAY, "14:00", 8)

    before = client.get(f"/slots?equipment_id=E1&date={DAY}").get_data(as_text=True)
    assert 'action="/bookings"' in before
    assert 'name="equipment_id" value="E1"' in before
    assert f'name="date" value="{DAY}"' in before
    assert set(CHECKBOX_PATTERN.findall(before)) == all_slots

    assert post_booking(client, slots=booked).status_code == 303
    after = client.get(f"/slots?equipment_id=E1&date={DAY}").get_data(as_text=True)
    assert set(CHECKBOX_PATTERN.findall(after)) == all_slots - set(booked)
