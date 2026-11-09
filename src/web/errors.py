"""HTTP 状态码的唯一映射点（§4 不变量、§11）。"""

from __future__ import annotations

from flask import render_template

from src.core.errors import (
    AppError,
    Conflict,
    Forbidden,
    NotFound,
    Unauthorized,
    Unavailable,
    Validation,
)

STATUS_BY_ERROR = {
    Validation: 400,
    Unauthorized: 401,
    Forbidden: 403,
    NotFound: 404,
    Conflict: 409,
    Unavailable: 503,
}


def status_for(error: AppError) -> int:
    return STATUS_BY_ERROR[type(error)]


def render_error(error: AppError, template: str = "error.html", **context):
    return render_template(template, error=error.message, **context), status_for(error)


def register_error_handlers(app) -> None:
    def handle(error: AppError):
        return render_template("error.html", error=error.message), status_for(error)

    for error_type in STATUS_BY_ERROR:
        app.register_error_handler(error_type, handle)