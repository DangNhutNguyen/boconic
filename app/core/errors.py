from typing import Any, Dict, Optional
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse

class ErrorCode:
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    COPY_UNAVAILABLE = "COPY_UNAVAILABLE"
    INVALID_STATE = "INVALID_STATE"
    ALREADY_EXISTS = "ALREADY_EXISTS"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"

class BoconicException(HTTPException):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(status_code=status_code, detail=message)
        self.code = code
        self.message = message
        self.details = details or {}

def create_error_response(
    code: str,
    message: str,
    status_code: int,
    details: Optional[Dict[str, Any]] = None,
    request_id: Optional[str] = None,
) -> JSONResponse:
    content = {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "request_id": request_id or "local",
        }
    }
    return JSONResponse(status_code=status_code, content=content)

async def boconic_exception_handler(request: Request, exc: BoconicException) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    return create_error_response(
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
        details=exc.details,
        request_id=request_id,
    )

async def generic_http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    code_map = {
        401: ErrorCode.UNAUTHORIZED,
        403: ErrorCode.FORBIDDEN,
        404: ErrorCode.NOT_FOUND,
        409: ErrorCode.CONFLICT,
        422: ErrorCode.VALIDATION_ERROR,
        429: ErrorCode.RATE_LIMITED,
        503: ErrorCode.SERVICE_UNAVAILABLE,
    }
    code = code_map.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
    return create_error_response(
        code=code,
        message=str(exc.detail),
        status_code=exc.status_code,
        request_id=request_id,
    )
