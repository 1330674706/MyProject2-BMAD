"""create_app()：读配置 → 打开数据库并迁移 → 注册蓝图 → 映射错误 → 记录请求。"""

from __future__ import annotations

import logging
from datetime import timedelta

from flask import Flask, g, request

from src.core.config import load_config
from src.data.db import close_db, initialize
from src.web.admin import bp as admin_bp
from src.web.auth import bp as auth_bp
from src.web.catalog import bp as catalog_bp
from src.web.csrf import current_csrf_token, set_csrf_cookie
from src.web.errors import register_error_handlers


def create_app() -> Flask:
    config = load_config()

    app = Flask(__name__, template_folder="src/templates", static_folder="src/static")
    app.config.update(
        SECRET_KEY=config.secret_key,
        LAB_DEFAULT_PASSWORD=config.default_password,
        LAB_DB_PATH=str(config.db_path),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=False,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
        SESSION_REFRESH_EACH_REQUEST=False,
    )
    app.logger.setLevel(logging.INFO)

    initialize(config.db_path)
    app.jinja_env.globals["csrf_token"] = current_csrf_token

    app.register_blueprint(auth_bp)
    app.register_blueprint(catalog_bp)
    app.register_blueprint(admin_bp)
    register_error_handlers(app)
    app.teardown_appcontext(close_db)

    @app.after_request
    def log_request(response):
        set_csrf_cookie(response)
        user = g.get("user")
        app.logger.info(
            "%s %s %s user=%s",
            request.method,
            request.path,
            response.status_code,
            user["id"] if user is not None else "-",
        )
        return response

    return app
