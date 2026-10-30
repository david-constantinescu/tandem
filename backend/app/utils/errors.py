from __future__ import annotations


class APIError(Exception):
    status = 400
    code = "bad_request"

    def __init__(self, message: str, *, code: str | None = None, status: int | None = None, details=None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status:
            self.status = status
        self.details = details


class NotFound(APIError):
    status = 404
    code = "not_found"


class Unauthorized(APIError):
    status = 401
    code = "unauthorized"


class Forbidden(APIError):
    status = 403
    code = "forbidden"


class Conflict(APIError):
    status = 409
    code = "conflict"


class ValidationFailed(APIError):
    status = 422
    code = "validation_failed"
