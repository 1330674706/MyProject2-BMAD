"""设备清单与逐 slot 占用视图路由（FR-2、FR-3）。"""

from __future__ import annotations

from flask import Blueprint, g, render_template, request, url_for

from src.app import equipment_service, slot_service
from src.core.errors import NotFound, Validation
from src.data.db import get_db
from src.web.auth import login_required
from src.web.errors import render_error

bp = Blueprint("catalog", __name__)


@bp.get("/equipments")
@login_required
def equipments():
    admin_url = url_for("admin.equipments") if g.user["role"] == "admin" else None
    return render_template(
        "equipments.html",
        equipments=equipment_service.list_equipments(get_db()),
        admin_url=admin_url,
    )


@bp.get("/slots")
@login_required
def slots():
    equipment_id = (request.args.get("equipment_id") or "").strip()
    day = (request.args.get("date") or "").strip()
    equipments = equipment_service.list_equipments(get_db())
    try:
        grid = slot_service.build_slot_grid(
            get_db(),
            equipment_id=equipment_id,
            day=day,
            viewer_id=g.user["id"],
        )
    except (Validation, NotFound) as error:
        return render_error(
            error,
            "slots.html",
            equipments=equipments,
            grid=None,
            selected_equipment_id=equipment_id,
            selected_date=day,
        )
    return render_template(
        "slots.html",
        equipments=equipments,
        grid=grid,
        selected_equipment_id=equipment_id,
        selected_date=grid.day,
    )
