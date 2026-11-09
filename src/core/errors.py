"""领域异常；HTTP 状态码只在 src/web/errors.py 映射。"""

from __future__ import annotations


class AppError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class Validation(AppError):
    pass


class Unauthorized(AppError):
    pass


class Forbidden(AppError):
    pass


class NotFound(AppError):
    pass


class Conflict(AppError):
    pass


class Unavailable(AppError):
    pass