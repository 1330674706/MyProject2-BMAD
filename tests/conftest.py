from __future__ import annotations

import pytest

from app import create_app


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "lab.db"
    monkeypatch.setenv("LAB_SECRET_KEY", "unit-test-secret-key-" + "0123456789abcdef" * 2)
    monkeypatch.setenv("LAB_DEFAULT_PASSWORD", "lab-default-2026")
    monkeypatch.setenv("LAB_DB_PATH", str(path))
    return path


@pytest.fixture
def app(db_path):
    application = create_app()
    application.config.update(TESTING=True)
    return application


@pytest.fixture
def client(app):
    return app.test_client()