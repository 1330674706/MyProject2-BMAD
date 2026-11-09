"""登录、注册、登出与每请求会话核对（FR-1、ADR-004）。"""

from __future__ import annotations

from functools import wraps

from flask import Blueprint, g, redirect, render_template, request, session, url_for

from src.app import auth_service
from src.core.errors import Conflict, Forbidden, Unauthorized, Validation
from src.data.db import get_db
from src.web.csrf import rotate_csrf_token, validate_csrf
from src.web.errors import render_error

bp = Blueprint("auth", __name__)


def _resolve_user():
    user = auth_service.current_user(get_db(), uid=session.get("uid"), pv=session.get("pv"))
    if user is None:
        raise Unauthorized("请先登录")
    g.user = user
    return user


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        _resolve_user()
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = _resolve_user()
        if user["role"] != "admin":
            raise Forbidden("仅管理员可执行该操作")
        return view(*args, **kwargs)

    return wrapped


@bp.get("/register")
def register_form():
    return render_template("register.html", error=None)


@bp.post("/register")
def register_submit():
    validate_csrf()
    try:
        auth_service.register(
            get_db(),
            student_no=request.form.get("student_no"),
            password=request.form.get("password"),
        )
    except (Validation, Conflict) as error:
        return render_error(error, "register.html")
    return redirect(url_for("auth.login_form"), code=303)


@bp.get("/login")
def login_form():
    return render_template("login.html", error=None)


@bp.post("/login")
def login_submit():
    validate_csrf()
    try:
        user = auth_service.login(
            get_db(),
            student_no=request.form.get("student_no"),
            password=request.form.get("password"),
        )
    except Unauthorized as error:
        return render_error(error, "login.html")

    session.clear()
    session.permanent = True
    session["uid"] = user["id"]
    session["role"] = user["role"]
    session["pv"] = user["password_version"]
    rotate_csrf_token()
    return redirect(url_for("catalog.equipments"), code=303)


@bp.post("/logout")
@login_required
def logout():
    validate_csrf()
    session.clear()
    return redirect(url_for("auth.login_form"), code=303)