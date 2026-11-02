"""FastAPI read-only web panel for the professor.

Connects to PostgreSQL using `UNICODE_PANEL_DATABASE_URL` (`unicode_panel` role),
validates Email + Password via HTTP Basic in constant time without triggering
browser pop-ups, exposes JSON endpoints under `/api/*`, and serves the React SPA
from `UNICODE_WEB_DIST_DIR`.
"""

import base64
import binascii
import secrets
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import AbstractContextManager, asynccontextmanager, contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse

from unicode.config import Settings, get_settings
from unicode.db import DictConnection, DictPool, create_pool, transaction
from unicode.services.grades import (
    GradeReportError,
    format_grades_csv,
    get_overview_stats,
    get_student_detail_report,
    get_unit_detail_report,
    list_student_grades_summary,
    list_unit_grades_for_export,
)

ConnFactory = Callable[[], AbstractContextManager[DictConnection]]


def _verify_basic_auth(auth_header: str | None, settings: Settings) -> str:
    """Validate Authorization: Basic base64(email:password) in constant time."""
    if not auth_header or not auth_header.lower().startswith("basic "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas.",
        )
    encoded = auth_header[6:].strip()
    try:
        decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas.",
        ) from None

    if ":" not in decoded:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas.",
        )

    provided_email, provided_password = decoded.split(":", 1)
    norm_provided_email = provided_email.strip().lower().encode("utf-8")
    norm_expected_email = settings.admin_email.strip().lower().encode("utf-8")

    email_ok = secrets.compare_digest(norm_provided_email, norm_expected_email)
    password_ok = secrets.compare_digest(
        provided_password.encode("utf-8"),
        settings.admin_password.encode("utf-8"),
    )
    if not (email_ok and password_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas.",
        )
    return settings.admin_email.strip().lower()


def create_app(
    *,
    settings: Settings | None = None,
    conn_factory: ConnFactory | None = None,
) -> FastAPI:
    """Create and configure the professor FastAPI application."""
    cfg = settings or get_settings()
    panel_pool: DictPool | None = None

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        nonlocal panel_pool
        if conn_factory is None:
            panel_pool = create_pool(
                cfg.panel_database_url,
                min_size=cfg.db_pool_min_size,
                max_size=cfg.db_pool_max_size,
            )
        try:
            yield
        finally:
            if panel_pool is not None:
                panel_pool.close()
                panel_pool = None

    app = FastAPI(
        title="UniCode - Painel do Professor",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    @contextmanager
    def default_conn_factory() -> Iterator[DictConnection]:
        nonlocal panel_pool
        if panel_pool is None:
            panel_pool = create_pool(
                cfg.panel_database_url,
                min_size=cfg.db_pool_min_size,
                max_size=cfg.db_pool_max_size,
            )
        with transaction(panel_pool) as conn:
            yield conn

    active_conn_factory: ConnFactory = conn_factory or default_conn_factory

    def require_admin(request: Request) -> str:
        return _verify_basic_auth(request.headers.get("authorization"), cfg)

    AdminDep = Annotated[str, Depends(require_admin)]

    @app.get("/api/auth/me")
    def auth_me(admin_email: AdminDep) -> dict[str, str]:
        return {"email": admin_email}

    @app.get("/api/overview")
    def api_overview(_admin: AdminDep) -> dict[str, Any]:
        with active_conn_factory() as conn:
            overview, units = get_overview_stats(conn)
        return {
            "stats": asdict(overview),
            "units": [asdict(u) for u in units],
        }

    @app.get("/api/students")
    def api_students(
        _admin: AdminDep,
        unit: Annotated[str | None, Query()] = None,
        class_group: Annotated[str | None, Query()] = None,
    ) -> dict[str, Any]:
        with active_conn_factory() as conn:
            students = list_student_grades_summary(
                conn, unit_code=unit, class_group=class_group
            )
        return {"students": [asdict(s) for s in students]}

    @app.get("/api/students/{registration}")
    def api_student_detail(_admin: AdminDep, registration: str) -> dict[str, Any]:
        try:
            with active_conn_factory() as conn:
                report = get_student_detail_report(conn, registration)
        except GradeReportError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
            ) from None
        return asdict(report)

    @app.get("/api/units/{code}")
    def api_unit_detail(_admin: AdminDep, code: str) -> dict[str, Any]:
        try:
            with active_conn_factory() as conn:
                report = get_unit_detail_report(conn, code)
        except GradeReportError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
            ) from None
        return asdict(report)

    @app.get("/api/export.csv")
    def api_export_csv(
        _admin: AdminDep,
        unit: Annotated[str, Query(min_length=1)],
        class_group: Annotated[str | None, Query()] = None,
    ) -> Response:
        try:
            with active_conn_factory() as conn:
                rows = list_unit_grades_for_export(
                    conn, unit, class_group=class_group
                )
        except GradeReportError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
            ) from None

        csv_content = format_grades_csv(rows)
        safe_unit = "".join(c for c in unit if c.isalnum() or c in ("-", "_"))
        filename = f"notas-{safe_unit or 'unidade'}.csv"
        return Response(
            content=csv_content,
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str) -> Response:
        if full_path.startswith("api/"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Endpoint não encontrado.",
            )
        dist_dir: Path = cfg.web_dist_dir.resolve()
        index_file = dist_dir / "index.html"
        if not index_file.is_file():
            return Response(
                content=(
                    "Frontend React não compilado. "
                    "Execute 'npm run build' na pasta web/."
                ),
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                media_type="text/plain; charset=utf-8",
            )

        if full_path:
            candidate = (dist_dir / full_path).resolve()
            if candidate.is_relative_to(dist_dir) and candidate.is_file():
                return FileResponse(candidate)

        return FileResponse(index_file)

    return app
