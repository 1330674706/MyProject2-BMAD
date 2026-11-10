"""预约提交路由：只解析表单并映射状态码（R1、ADR-003）。"""

from __future__ import annotations

from flask import Blueprint, g, redirect, render_template, request, url_for

from src.app import booking_service, equipment_service, slot_service
from src.core.errors import AppError, Conflict, NotFound, Validation
from src.data.db import get_db
from src.web.auth import login_required
from src.web.csrf import validate_csrf
from src.web.errors import render_error

bp = Blueprint("bookings", __name__)


@bp.get("/bookings/mine")
@login_required
def mine():
    return render_template(
        "bookings_mine.html",
        bookings=booking_service.list_my_bookings(get_db(), g.user["id"]),
    )


@bp.post("/bookings/<id>/cancel")
@login_required
def cancel(id):
    validate_csrf()
    try:
        booking_service.cancel_booking(get_db(), g.user["id"], id)
    except Validation as error:
        return render_error(
            error,
            "bookings_mine.html",
            bookings=booking_service.list_my_bookings(get_db(), g.user["id"]),
        )
    except AppError as error:
        return render_error(error)
    return redirect(url_for("bookings.mine"), code=303)


def _render_slots(error, *, equipment_id, day, grid=None):
    return render_error(
        error,
        "slots.html",
        equipments=equipment_service.list_equipments(get_db()),
        grid=grid,
        selected_equipment_id=equipment_id,
        selected_date=day,
    )


def _render_conflict(error, *, equipment_id, day, submitted_slots):
    grid = None
    try:
        grid = slot_service.build_slot_grid(
            get_db(),
            equipment_id=equipment_id,
            day=day,
            viewer_id=g.user["id"],
            conflicted_slots=error.conflict_slots,
            selected_slots=submitted_slots,
        )
    except (Validation, NotFound):
        grid = None
    return _render_slots(error, equipment_id=equipment_id, day=day, grid=grid)


@bp.post("/bookings")
@login_required
def create():
    validate_csrf()
    equipment_id = (request.form.get("equipment_id") or "").strip()
    day = (request.form.get("date") or "").strip()
    submitted_slots = request.form.getlist("slot")
    try:
        booking_service.create_booking(
            get_db(),
            g.user["id"],
            equipment_id,
            submitted_slots,
        )
    except Conflict as error:
        return _render_conflict(
            error,
            equipment_id=equipment_id,
            day=day,
            submitted_slots=submitted_slots,
        )
    except Validation as error:
        return _render_slots(error, equipment_id=equipment_id, day=day)
    if day:
        return redirect(url_for("catalog.slots", equipment_id=equipment_id, date=day), code=303)
    return redirect(url_for("catalog.equipments"), code=303)
