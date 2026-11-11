"""管理员路由：周视图、学生检索、改单、账号运维与设备维护。"""

from __future__ import annotations

from flask import Blueprint, Response, current_app, g, redirect, render_template, request, url_for

from src.app import (
    admin_service,
    audit,
    auth_service,
    booking_service,
    equipment_service,
    export_service,
)
from src.core.errors import Conflict, NotFound, Validation
from src.data.db import get_db
from src.web.auth import admin_required
from src.web.csrf import validate_csrf
from src.web.errors import render_error

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.get("/export")
@admin_required
def export_week():
    try:
        export = export_service.build_week_export(get_db(), week=request.args.get("week"))
    except Validation as error:
        return render_error(
            error,
            "admin_week.html",
            view=None,
            selected_week=(request.args.get("week") or "").strip(),
        )
    return Response(
        export.body,
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{export.filename}"'},
    )


@bp.get("/audit")
@admin_required
def audit_log():
    return render_template("admin_audit.html", view=audit.list_audit(get_db()))


@bp.get("/week")
@admin_required
def week():
    try:
        view = admin_service.build_week_view(
            get_db(),
            week=request.args.get("week"),
            viewer_id=g.user["id"],
        )
    except Validation as error:
        return render_error(
            error,
            "admin_week.html",
            view=None,
            selected_week=(request.args.get("week") or "").strip(),
        )
    return render_template("admin_week.html", view=view, selected_week=view.monday)


def _render_edit(
    error=None,
    *,
    booking_id,
    day,
    selected_slots=None,
    conflicted_slots=(),
):
    db = get_db()
    conflict_pending = isinstance(error, Conflict)
    try:
        view = admin_service.build_booking_edit_view(
            db,
            booking_id=booking_id,
            viewer_id=g.user["id"],
            day=day,
            selected_slots=selected_slots,
            conflicted_slots=conflicted_slots,
            conflict_pending=conflict_pending,
        )
    except Validation as bad_day:
        view = admin_service.build_booking_edit_view(
            db,
            booking_id=booking_id,
            viewer_id=g.user["id"],
            selected_slots=selected_slots,
            conflicted_slots=conflicted_slots,
            conflict_pending=conflict_pending,
        )
        error = error or bad_day
    if error is None:
        return render_template("admin_booking_edit.html", view=view)
    return render_error(error, "admin_booking_edit.html", view=view)


@bp.get("/bookings/<id>/edit")
@admin_required
def edit_booking_form(id):
    return _render_edit(booking_id=id, day=request.args.get("date"))


@bp.post("/bookings/<id>/edit")
@admin_required
def edit_booking(id):
    validate_csrf()
    day = (request.form.get("date") or "").strip()
    submitted_slots = request.form.getlist("slot")
    week_monday = admin_service.booking_week_monday(get_db(), id)
    try:
        booking_service.edit_booking(
            get_db(),
            g.user["id"],
            id,
            (request.form.get("equipment_id") or "").strip(),
            submitted_slots,
        )
    except Conflict as error:
        return _render_edit(
            error,
            booking_id=id,
            day=day,
            selected_slots=submitted_slots,
            conflicted_slots=error.conflict_slots,
        )
    except Validation as error:
        return _render_edit(
            error,
            booking_id=id,
            day=day,
            selected_slots=submitted_slots,
        )
    return redirect(url_for("admin.week", week=week_monday), code=303)


def _render_lock(
    error=None,
    *,
    equipment_id,
    day,
    selected_slots=None,
    conflicted_slots=(),
):
    db = get_db()
    try:
        view = admin_service.build_lock_view(
            db,
            equipment_id=equipment_id,
            viewer_id=g.user["id"],
            day=day,
            selected_slots=selected_slots or (),
            conflicted_slots=conflicted_slots,
        )
    except Validation as bad_day:
        view = admin_service.build_lock_view(
            db,
            equipment_id=equipment_id,
            viewer_id=g.user["id"],
            selected_slots=selected_slots or (),
            conflicted_slots=conflicted_slots,
        )
        error = error or bad_day
    if error is None:
        return render_template("admin_lock.html", view=view)
    return render_error(error, "admin_lock.html", view=view)


@bp.get("/equipments/<id>/lock")
@admin_required
def lock_form(id):
    return _render_lock(equipment_id=id, day=request.args.get("date"))


@bp.post("/equipments/<id>/lock")
@admin_required
def lock_slots(id):
    validate_csrf()
    day = (request.form.get("date") or "").strip()
    submitted = request.form.getlist("slot")
    try:
        validated = booking_service.lock_slots(get_db(), g.user["id"], id, submitted)
        week = admin_service.week_monday_for_slots(validated)
    except Conflict as error:
        return _render_lock(
            error,
            equipment_id=id,
            day=day,
            selected_slots=submitted,
            conflicted_slots=error.conflict_slots,
        )
    except Validation as error:
        return _render_lock(error, equipment_id=id, day=day, selected_slots=submitted)
    return redirect(url_for("admin.week", week=week), code=303)


@bp.post("/equipments/<id>/unlock")
@admin_required
def unlock_slots(id):
    validate_csrf()
    day = (request.form.get("date") or "").strip()
    submitted = request.form.getlist("slot")
    try:
        validated = booking_service.unlock_slots(get_db(), g.user["id"], id, submitted)
        week = admin_service.week_monday_for_slots(validated)
    except NotFound as error:
        return _render_lock(error, equipment_id=id, day=day, selected_slots=submitted)
    except Validation as error:
        return _render_lock(error, equipment_id=id, day=day, selected_slots=submitted)
    return redirect(url_for("admin.week", week=week), code=303)


@bp.get("/users")
@admin_required
def users():
    return render_template(
        "admin_users.html",
        result=admin_service.search_student_bookings(
            get_db(),
            request.args.get("student_no"),
        ),
    )


@bp.get("/equipments")
@admin_required
def equipments():
    return render_template(
        "admin_equipments.html",
        equipments=equipment_service.list_equipments(get_db()),
    )


@bp.post("/equipments")
@admin_required
def create_equipment():
    validate_csrf()
    try:
        equipment_service.create_equipment(
            get_db(),
            name=request.form.get("name"),
            open_start=request.form.get("open_start"),
            open_end=request.form.get("open_end"),
            actor_id=g.user["id"],
        )
    except (Validation, Conflict) as error:
        return render_error(
            error,
            "admin_equipments.html",
            equipments=equipment_service.list_equipments(get_db()),
        )
    return redirect(url_for("admin.equipments"), code=303)


@bp.post("/equipments/<id>/window")
@admin_required
def update_window(id):
    validate_csrf()
    try:
        equipment_service.update_window(
            get_db(),
            equipment_id=id,
            name=request.form.get("name"),
            open_start=request.form.get("open_start"),
            open_end=request.form.get("open_end"),
            actor_id=g.user["id"],
        )
    except (Validation, Conflict) as error:
        return render_error(
            error,
            "admin_equipments.html",
            equipments=equipment_service.list_equipments(get_db()),
        )
    return redirect(url_for("admin.equipments"), code=303)


@bp.post("/users/<id>/reset-password", provide_automatic_options=False)
@admin_required
def reset_password(id):
    validate_csrf()
    auth_service.reset_password(
        get_db(),
        target_user_id=id,
        actor_id=g.user["id"],
        default_password=current_app.config["LAB_DEFAULT_PASSWORD"],
    )
    return redirect(url_for("catalog.equipments"), code=303)
