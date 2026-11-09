"""Story 1.3 验收测试：逐 slot 占用状态视图。

每条 AC 逐条对应 `_bmad-output/planning-artifacts/epics.md` 的 Story 1.3。
测试只通过公开入口（`build_slot_grid()`、`_slot_grid.html` 与 HTTP 路由）观察行为。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from werkzeug.security import generate_password_hash

from src.core.timeutil import local_to_utc, now_utc, utc_to_local

ROOT = Path(__file__).resolve().parents[1]
DAY = "2030-01-01"
FAR_DAY = "2030-01-10"
NOW_BEFORE_DAY = "2029-12-31T00:00:00Z"
NOW_MIDDAY = "2030-01-01T04:00:00Z"
SIX_STATES = {
    "free",
    "booked_by_self",
    "booked_by_other",
    "locked",
    "closed_past",
    "closed_window",
}
A = "a" * 32
B = "b" * 32
PASSWORD_HASH = generate_password_hash("P@ssw0rd-lab")


def slot_api():
    from src.app import slot_service

    assert hasattr(slot_service, "SIX_STATES"), "slot_service 尚未提供六态常量"
    assert hasattr(slot_service, "SlotCell"), "slot_service 尚未提供 SlotCell"
    assert hasattr(slot_service, "build_slot_grid"), "slot_service 尚未提供 build_slot_grid()"
    return slot_service


def connect(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def seed_user(db_path, user_id, student_no):
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO user (id, student_no, role, password_hash, password_version, active, created_at)"
            " VALUES (?, ?, 'student', ?, 1, 1, ?)",
            (user_id, student_no, PASSWORD_HASH, "2026-11-09T00:00:00Z"),
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


def seed_booking(db_path, *, booking_id, owner_id, times, equipment_id="E1", day=DAY):
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO booking (id, owner_id, equipment_id, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (booking_id, owner_id, equipment_id, "2026-11-09T00:00:00Z", "2026-11-09T00:00:00Z"),
        )
        for hhmm in times:
            conn.execute(
                "INSERT INTO occupancy (equipment_id, slot_start, kind, booking_id, created_at)"
                " VALUES (?, ?, 'booking', ?, ?)",
                (equipment_id, utc_at(day, hhmm), booking_id, "2026-11-09T00:00:00Z"),
            )
        conn.commit()
    finally:
        conn.close()


def seed_lock(db_path, hhmm, equipment_id="E1", day=DAY):
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO occupancy (equipment_id, slot_start, kind, booking_id, created_at)"
            " VALUES (?, ?, 'lock', NULL, ?)",
            (equipment_id, utc_at(day, hhmm), "2026-11-09T00:00:00Z"),
        )
        conn.commit()
    finally:
        conn.close()


def service_grid(db_path, *, viewer_id=A, now=NOW_BEFORE_DAY, day=DAY, equipment_id="E1"):
    slot_service = slot_api()
    conn = connect(db_path)
    try:
        return slot_service.build_slot_grid(
            conn,
            equipment_id=equipment_id,
            day=day,
            viewer_id=viewer_id,
            now=now,
        )
    finally:
        conn.close()


def login_as(client, user_id, role="student", password_version=1):
    with client.session_transaction() as session:
        session["uid"] = user_id
        session["role"] = role
        session["pv"] = password_version


def target_day(days_ahead=2):
    return (utc_to_local(now_utc()) + timedelta(days=days_ahead)).date().isoformat()


def test_six_states_are_final():
    slot_service = slot_api()

    assert set(slot_service.SIX_STATES) == SIX_STATES


def test_slot_cell_rejects_state_outside_contract():
    slot_service = slot_api()

    with pytest.raises(ValueError):
        slot_service.SlotCell(start=NOW_BEFORE_DAY, local_time="08:00", state="pending")


def test_booked_states_distinguish_self_and_other(app, db_path):
    seed_user(db_path, A, "2025001")
    seed_user(db_path, B, "2025002")
    seed_equipment(db_path)
    seed_booking(db_path, booking_id="1" * 32, owner_id=A, times=["14:00"])
    seed_booking(db_path, booking_id="2" * 32, owner_id=B, times=["14:30"])

    grid = service_grid(db_path, viewer_id=A)

    assert (grid["14:00"].state, grid["14:30"].state) == ("booked_by_self", "booked_by_other")


def test_same_booking_is_other_from_another_student(app, db_path):
    seed_user(db_path, A, "2025001")
    seed_user(db_path, B, "2025002")
    seed_equipment(db_path)
    seed_booking(db_path, booking_id="1" * 32, owner_id=A, times=["14:00"])

    grid = service_grid(db_path, viewer_id=B)

    assert grid["14:00"].state == "booked_by_other"


def test_past_slots_are_closed_past_and_override_occupancy(app, db_path):
    seed_user(db_path, A, "2025001")
    seed_equipment(db_path)
    seed_lock(db_path, "09:00")
    seed_booking(db_path, booking_id="1" * 32, owner_id=A, times=["10:00"])

    grid = service_grid(db_path, viewer_id=A, now=NOW_MIDDAY)

    assert all(cell.state == "closed_past" for cell in grid if cell.start < NOW_MIDDAY)
    assert grid["09:00"].state == "closed_past"
    assert grid["10:00"].state == "closed_past"
    assert grid["12:30"].state == "free"


def test_slots_beyond_seven_days_are_closed_window(app, db_path):
    seed_equipment(db_path, open_start="09:00", open_end="12:00")
    seed_lock(db_path, "09:00", day=FAR_DAY)

    grid = service_grid(db_path, now=NOW_MIDDAY, day=FAR_DAY)

    assert grid["09:00"].state == "closed_window"
    assert all(cell.state == "closed_window" for cell in grid)


def test_locked_slot_is_locked_for_student(app, db_path):
    seed_user(db_path, A, "2025001")
    seed_equipment(db_path)
    seed_lock(db_path, "16:00")

    grid = service_grid(db_path, viewer_id=A)

    assert grid["16:00"].state == "locked"
    assert grid["17:00"].state == "free"


def test_occupancy_from_other_equipment_does_not_leak(app, db_path):
    seed_user(db_path, A, "2025001")
    seed_equipment(db_path, "E1")
    seed_equipment(db_path, "E2")
    seed_booking(db_path, booking_id="1" * 32, owner_id=A, times=["14:00"], equipment_id="E2")

    grid = service_grid(db_path, viewer_id=A, equipment_id="E1")

    assert grid["14:00"].state == "free"


def test_slots_page_renders_one_data_state_per_cell_and_only_six_states(app, db_path):
    day = target_day()
    seed_user(db_path, A, "2025001")
    seed_user(db_path, B, "2025002")
    seed_equipment(db_path)
    seed_booking(db_path, booking_id="1" * 32, owner_id=A, times=["14:00"], day=day)
    seed_booking(db_path, booking_id="2" * 32, owner_id=B, times=["14:30"], day=day)
    seed_lock(db_path, "16:00", day=day)
    client = app.test_client()
    login_as(client, A)

    resp = client.get(f"/slots?equipment_id=E1&date={day}")
    html = resp.get_data(as_text=True)
    grid = service_grid(db_path, viewer_id=A, now=now_utc(), day=day)
    states = {cell.state for cell in grid}

    assert resp.status_code == 200
    assert states <= SIX_STATES
    assert html.count("data-state=") == len(grid.cells)
    assert 'data-state="booked_by_self"' in html
    assert 'data-state="booked_by_other"' in html
    assert 'data-state="locked"' in html


def test_slots_response_has_no_push_or_polling(app, db_path):
    day = target_day()
    seed_user(db_path, A, "2025001")
    seed_equipment(db_path)
    client = app.test_client()
    login_as(client, A)

    resp = client.get(f"/slots?equipment_id=E1&date={day}")
    html = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert "Upgrade" not in resp.headers
    assert "text/event-stream" not in resp.headers.get("Content-Type", "")
    assert "EventSource" not in html
    assert "setInterval" not in html


def test_slot_grid_partial_renders_only_supplied_states(app):
    slot_service = slot_api()
    template_path = ROOT / "src" / "templates" / "_slot_grid.html"
    assert template_path.exists(), "_slot_grid.html 尚未创建"
    cells = [
        slot_service.SlotCell(
            start=f"2030-01-01T0{index}:00:00Z",
            local_time=f"0{index + 8}:00",
            state="locked",
        )
        for index in range(3)
    ]

    out = app.jinja_env.get_template("_slot_grid.html").render(
        grid=SimpleNamespace(cells=cells)
    )

    assert out.count('data-state="locked"') == 3
    assert out.count("data-state=") == 3


def test_core_page_declares_viewport_and_css_has_mobile_breakpoint(app, db_path):
    day = target_day()
    seed_user(db_path, A, "2025001")
    seed_equipment(db_path)
    client = app.test_client()
    login_as(client, A)

    html = client.get(f"/slots?equipment_id=E1&date={day}").get_data(as_text=True)
    css = (ROOT / "src" / "static" / "app.css").read_text(encoding="utf-8")

    assert 'name="viewport"' in html and "width=device-width" in html
    assert "@media" in css
    assert "max-width: 480px" in css


def test_slots_requires_login(app):
    client = app.test_client()

    resp = client.get(f"/slots?equipment_id=E1&date={target_day()}")

    assert resp.status_code == 401


def test_unknown_equipment_returns_404(app, db_path):
    seed_user(db_path, A, "2025001")
    client = app.test_client()
    login_as(client, A)

    resp = client.get(f"/slots?equipment_id=MISSING&date={target_day()}")

    assert resp.status_code == 404


def test_invalid_date_returns_400(app, db_path):
    seed_user(db_path, A, "2025001")
    seed_equipment(db_path)
    client = app.test_client()
    login_as(client, A)

    resp = client.get("/slots?equipment_id=E1&date=not-a-date")

    assert resp.status_code == 400

