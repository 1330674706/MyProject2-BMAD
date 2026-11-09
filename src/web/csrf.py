"""CSRF token：匿名表单用签名 token，登录后存入会话并轮换（ADR-003、ADR-004）。"""

from __future__ import annotations

import hmac
import secrets

from flask import current_app, request, session
from itsdangerous import BadSignature, URLSafeTimedSerializer

from src.core.errors import Validation

SALT = "lab-csrf"
MAX_AGE_SECONDS = 12 * 60 * 60
SESSION_KEY = "csrf_token"


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.secret_key, salt=SALT)


def current_csrf_token() -> str:
    token = session.get(SESSION_KEY)
    if token:
        return token
    return _serializer().dumps(secrets.token_hex(16))


def rotate_csrf_token() -> str:
    session[SESSION_KEY] = secrets.token_urlsafe(32)
    return session[SESSION_KEY]


def validate_csrf() -> None:
    submitted = request.form.get("csrf_token", "")
    if not submitted:
        raise Validation("缺少 CSRF token")

    expected = session.get(SESSION_KEY)
    if expected:
        if not hmac.compare_digest(submitted, expected):
            raise Validation("CSRF token 不匹配")
        return

    try:
        _serializer().loads(submitted, max_age=MAX_AGE_SECONDS)
    except BadSignature:
        raise Validation("CSRF token 无效") from None