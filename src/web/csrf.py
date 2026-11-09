"""CSRF token：签名 token 的独立 cookie + 表单字段 double-submit 校验（ADR-003、ADR-004）。

token 不写入会话：匿名 GET 表单也只会拿到 `csrf` cookie，401 响应不会因此带出 session cookie。
"""

from __future__ import annotations

import hmac
import secrets

from flask import current_app, g, request
from itsdangerous import BadSignature, URLSafeTimedSerializer

from src.core.errors import Validation

SALT = "lab-csrf"
COOKIE_NAME = "csrf"
MAX_AGE_SECONDS = 12 * 60 * 60


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.secret_key, salt=SALT)


def _new_token() -> str:
    return _serializer().dumps(secrets.token_hex(16))


def current_csrf_token() -> str:
    token = g.get("csrf_token")
    if token is not None:
        return token
    token = request.cookies.get(COOKIE_NAME)
    if token is not None:
        try:
            _serializer().loads(token, max_age=MAX_AGE_SECONDS)
        except BadSignature:
            token = _new_token()
            g.csrf_cookie_dirty = True
        else:
            g.csrf_cookie_dirty = False
    else:
        token = _new_token()
        g.csrf_cookie_dirty = True
    g.csrf_token = token
    return token


def rotate_csrf_token() -> str:
    token = _new_token()
    g.csrf_token = token
    g.csrf_cookie_dirty = True
    return token


def set_csrf_cookie(response) -> None:
    token = g.get("csrf_token")
    if token is None:
        return
    if g.get("csrf_cookie_dirty") or request.cookies.get(COOKIE_NAME) != token:
        response.set_cookie(
            COOKIE_NAME,
            token,
            max_age=MAX_AGE_SECONDS,
            httponly=True,
            samesite="Lax",
            path="/",
            secure=False,
        )


def validate_csrf() -> None:
    submitted = request.form.get("csrf_token", "")
    expected = request.cookies.get(COOKIE_NAME, "")
    if not submitted or not expected:
        raise Validation("CSRF token 无效")
    try:
        _serializer().loads(submitted, max_age=MAX_AGE_SECONDS)
    except BadSignature:
        raise Validation("CSRF token 无效") from None
    if not hmac.compare_digest(submitted, expected):
        raise Validation("CSRF token 不匹配")
