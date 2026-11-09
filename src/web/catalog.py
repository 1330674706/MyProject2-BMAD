"""设备与 slot 路由的鉴权骨架（FR-2 / FR-3 由 Story 1.2、1.3 填充）。"""

from __future__ import annotations

from flask import Blueprint, render_template

from src.web.auth import login_required

bp = Blueprint("catalog", __name__)


@bp.get("/equipments")
@login_required
def equipments():
    return render_template("placeholder.html", title="设备清单")


@bp.get("/slots")
@login_required
def slots():
    return render_template("placeholder.html", title="slot 视图")