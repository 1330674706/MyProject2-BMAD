"""设备清单与 slot 路由（FR-2；slot 视图由 Story 1.3 填充）。"""

from __future__ import annotations

from flask import Blueprint, g, render_template, url_for

from src.app import equipment_service
from src.data.db import get_db
from src.web.auth import login_required

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
    return render_template("placeholder.html", title="slot 视图")
