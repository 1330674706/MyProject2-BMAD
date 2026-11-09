"""审计 before_json / after_json 的字段白名单（NFR-4、§10.2）。

白名单之外的字段一律拒绝写入，而不是过滤掉——黑名单过滤 password 是明确禁止的做法。
"""

from __future__ import annotations

import json

ALLOWED_FIELDS = {
    "user": frozenset({"student_no", "role", "active", "password_version"}),
}


def dump_fields(target_type: str, values: dict) -> str:
    allowed = ALLOWED_FIELDS[target_type]
    unexpected = set(values) - allowed
    if unexpected:
        raise ValueError(f"{target_type} 审计字段不在白名单: {sorted(unexpected)}")
    return json.dumps(values, ensure_ascii=False, sort_keys=True)