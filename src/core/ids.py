"""业务主键统一为 uuid4().hex（§11）。"""

from __future__ import annotations

from uuid import uuid4


def new_id() -> str:
    return uuid4().hex