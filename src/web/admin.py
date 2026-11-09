"""管理员账号运维路由；本周视图由 Story 3.1 交付。"""

from __future__ import annotations

from flask import Blueprint, current_app, g, redirect, url_for

from src.app import auth_service
from src.data.db import get_db
from src.web.auth import admin_required
from src.web.csrf import validate_csrf

bp = Blueprint("admin", __name__, url_prefix="/admin")


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