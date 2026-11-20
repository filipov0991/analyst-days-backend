import logging
import traceback

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

logger = logging.getLogger(__name__)


class APIException(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


def error_response(status, code, message, details=None):
    return JSONResponse(status_code=status, content={"error": {
        "code": code, "message": message, "details": details or []}})


def internal_error(exc: Exception):
    # Do not log exception text, SQL parameters, request headers, or local variables.
    frames = traceback.extract_tb(exc.__traceback__)
    logger.error("Unhandled %s at %s", type(exc).__name__,
                 " -> ".join(f"{f.filename}:{f.lineno}:{f.name}" for f in frames))
    return error_response(500, "INTERNAL_ERROR", "Внутренняя ошибка сервера")


def register_handlers(app):
    @app.exception_handler(APIException)
    async def api_error(request: Request, exc: APIException):
        return error_response(exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Fixed messages avoid echoing values supplied by the client.
        details = [{"field": ".".join(str(part) for part in error["loc"]),
                    "message": "Некорректное значение параметра"} for error in exc.errors()]
        return error_response(422, "VALIDATION_ERROR", "Ошибка валидации", details)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return error_response(exc.status_code, "HTTP_ERROR", "Запрос не может быть обработан")
