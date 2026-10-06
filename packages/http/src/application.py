from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from kitchen_core.db import get_engine
from kitchen_core.errors import DomainError
from kitchen_core.settings import get_settings
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


class HealthResponse(BaseModel):
    status: str
    version: str = "0.1.0"


class FieldIssue(BaseModel):
    loc: list[str | int]
    msg: str
    type: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    fields: list[FieldIssue] | None = None


class ErrorResponse(BaseModel):
    detail: ErrorDetail


def configure_app(title: str) -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=title,
        version="0.1.0",
        responses={
            400: {"model": ErrorResponse},
            401: {"model": ErrorResponse},
            403: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            429: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
        },
    )
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
        )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Request-ID"] = str(uuid4())
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError):
        return JSONResponse(
            status_code=exc.status, content={"detail": {"code": exc.code, "message": exc.message}}
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "detail": {
                    "code": "validation_error",
                    "message": "Check the submitted fields",
                    "fields": [
                        {"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]}
                        for e in exc.errors()
                    ],
                }
            },
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error(request: Request, exc: IntegrityError):
        return JSONResponse(
            status_code=409,
            content={
                "detail": {
                    "code": "conflict",
                    "message": "This change conflicts with an existing record",
                }
            },
        )

    @app.get("/health", response_model=HealthResponse, tags=["Health"])
    def health():
        return HealthResponse(status="ok")

    @app.get("/ready", response_model=HealthResponse, tags=["Health"])
    def ready():
        try:
            with get_engine().connect() as connection:
                revision = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar()
            if revision != "0004_contact_phones":
                raise DomainError(
                    503, "migration_required", "Apply the required database migration"
                )
        except DomainError:
            raise
        except Exception as exc:
            raise DomainError(503, "database_unavailable", "Database is not ready") from exc
        return HealthResponse(status="ready")

    return app
