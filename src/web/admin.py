"""管理员路由：账号运维、设备维护；本周视图由 Story 3.1 交付。"""

from __future__ import annotations

from flask import Blueprint, current_app, g, redirect, render_template, request, url_for

from src.app import admin_service, auth_service, equipment_service
from src.core.errors import Conflict, Validation
from src.data.db import get_db
from src.web.auth import admin_required
from src.web.csrf import validate_csrf
from src.web.errors import render_error

bp = Blueprint("admin", __name__, url_prefix="/admin")


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
