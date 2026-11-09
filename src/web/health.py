"""GET /health：免鉴权的可用性探针（architecture §15.1、NFR-2）。"""

from __future__ import annotations

from flask import Blueprint

from src.data.db import get_db

bp = Blueprint("health", __name__)


@bp.get("/health")
def health():
    get_db().execute("SELECT 1").fetchone()
    return {"status": "ok"}, 200
