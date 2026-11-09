"""预约提交路由：只解析表单并映射状态码（R1、ADR-003）。"""

from __future__ import annotations

from flask import Blueprint, g, redirect, request, url_for

from src.app import booking_service, equipment_service
from src.core.errors import Conflict, Validation
from src.data.db import get_db
from src.web.auth import login_required
from src.web.csrf import validate_csrf
from src.web.errors import render_error

bp = Blueprint("bookings", __name__)


@bp.post("/bookings")
@login_required
def create():
    validate_csrf()
    equipment_id = (request.form.get("equipment_id") or "").strip()
    day = (request.form.get("date") or "").strip()
    try:
        booking_service.create_booking(
            get_db(),
            g.user["id"],
            equipment_id,
            request.form.getlist("slot"),
        )
    except (Validation, Conflict) as error:
        return render_error(
            error,
            "slots.html",
            equipments=equipment_service.list_equipments(get_db()),
            grid=None,
            selected_equipment_id=equipment_id,
            selected_date=day,
        )
    if day:
        return redirect(url_for("catalog.slots", equipment_id=equipment_id, date=day), code=303)
    return redirect(url_for("catalog.equipments"), code=303)
