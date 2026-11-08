import base64
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from tests.support import AsgiTestClient
from unicode.cli_web import app as cli_web_app
from unicode.config import Settings
from unicode.db import DictConnection
from unicode.web import create_app


class FakeApiCursor:
    def __init__(
        self,
        *,
        one: dict[str, Any] | None = None,
        many: list[dict[str, Any]] | None = None,
    ) -> None:
        self._one = one
        self._many = many or []

    def fetchone(self) -> dict[str, Any] | None:
        return self._one

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._many)


class FakeApiConn:
    def __init__(self, responses: list[FakeApiCursor]) -> None:
        self._responses = list(responses)
        self.queries: list[tuple[str, Any]] = []

    def execute(self, query: str, params: Any = None) -> FakeApiCursor:
        self.queries.append((query, params))
        if not self._responses:
            raise AssertionError(f"Unexpected query: {query}")
        return self._responses.pop(0)


def _make_settings(tmp_path: Path | None = None) -> Settings:
    dist_dir = tmp_path / "dist" if tmp_path is not None else Path("nonexistent-dist")
    return Settings(
        admin_email="admin@unicode.local",
        admin_password="secret-password",
        web_dist_dir=dist_dir,
    )


def _make_client(
    responses: list[FakeApiCursor] | None = None,
    *,
    settings: Settings | None = None,
) -> tuple[AsgiTestClient, FakeApiConn]:
    fake_conn = FakeApiConn(responses or [])

    @contextmanager
    def conn_factory() -> Iterator[DictConnection]:
        yield fake_conn  # type: ignore[misc]

    app = create_app(
        settings=settings or _make_settings(),
        conn_factory=conn_factory,
    )
    return AsgiTestClient(app), fake_conn


def test_auth_missing_or_malformed_headers_return_401_without_www_authenticate() -> None:
    client, _ = _make_client()

    # Missing header
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401
    assert "www-authenticate" not in resp.headers
    assert resp.json() == {"detail": "Credenciais inválidas."}

    # Non-Basic scheme
    resp = client.get("/api/auth/me", headers={"Authorization": "Bearer some-token"})
    assert resp.status_code == 401
    assert "www-authenticate" not in resp.headers

    # Invalid base64
    resp = client.get("/api/auth/me", headers={"Authorization": "Basic %%%notbase64%%%"})
    assert resp.status_code == 401
    assert "www-authenticate" not in resp.headers

    # Base64 without colon separator
    no_colon = base64.b64encode(b"admin_without_colon").decode("ascii")
    resp = client.get("/api/auth/me", headers={"Authorization": f"Basic {no_colon}"})
    assert resp.status_code == 401
    assert "www-authenticate" not in resp.headers


def test_auth_wrong_email_or_password_returns_401() -> None:
    client, _ = _make_client()

    resp_email = client.get(
        "/api/auth/me",
        basic_auth=("wrong@unicode.local", "secret-password"),
    )
    assert resp_email.status_code == 401
    assert "www-authenticate" not in resp_email.headers
    assert resp_email.json() == {"detail": "Credenciais inválidas."}

    resp_pass = client.get(
        "/api/auth/me",
        basic_auth=("admin@unicode.local", "wrong-password"),
    )
    assert resp_pass.status_code == 401
    assert "www-authenticate" not in resp_pass.headers


def test_auth_me_accepts_valid_credentials_and_normalizes_email() -> None:
    client, _ = _make_client()

    resp = client.get(
        "/api/auth/me",
        basic_auth=("  ADMIN@UNICODE.LOCAL  ", "secret-password"),
    )
    assert resp.status_code == 200
    assert resp.json() == {"email": "admin@unicode.local"}


def test_api_overview_returns_stats_and_units() -> None:
    client, _ = _make_client(
        [
            FakeApiCursor(
                one={
                    "total_students": 30,
                    "total_units": 2,
                    "active_questions": 8,
                    "submissions_today": 11,
                    "approved_assignments": 18,
                    "decided_assignments": 24,
                }
            ),
            FakeApiCursor(
                many=[
                    {
                        "code": "unit-01",
                        "title": "Variáveis e Expressões",
                        "active_questions": 4,
                        "students_started": 20,
                        "average_points": Decimal("0.80"),
                    }
                ]
            ),
        ]
    )

    resp = client.get(
        "/api/overview",
        basic_auth=("admin@unicode.local", "secret-password"),
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["stats"]["total_students"] == 30
    assert payload["stats"]["approval_rate"] == 75.0
    assert len(payload["units"]) == 1
    assert payload["units"][0]["code"] == "unit-01"
    assert payload["units"][0]["average_points"] == 0.8


def test_api_students_supports_unit_and_class_group_filters() -> None:
    client, conn = _make_client(
        [
            FakeApiCursor(
                many=[
                    {
                        "registration": "20240001",
                        "email": "ana@edu.br",
                        "name": "Ana",
                        "class_group": "T01",
                    }
                ]
            ),
            FakeApiCursor(
                many=[
                    {
                        "registration": "20240001",
                        "unit": "unit-01",
                        "points": Decimal("1.0"),
                    }
                ]
            ),
        ]
    )

    resp = client.get(
        "/api/students?unit=unit-01&class_group=T01",
        basic_auth=("admin@unicode.local", "secret-password"),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["students"]) == 1
    assert data["students"][0]["registration"] == "20240001"
    assert data["students"][0]["grades_by_unit"] == {"unit-01": 1.0}
    assert conn.queries[0][1] == ("T01",)
    assert conn.queries[1][1] == ("unit-01",)


def test_api_student_detail_returns_200_and_404_when_missing() -> None:
    now = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
    client, _ = _make_client(
        [
            FakeApiCursor(
                one={
                    "registration": "20240001",
                    "email": "ana@edu.br",
                    "name": "Ana",
                    "class_group": "T01",
                    "created_at": now,
                }
            ),
            FakeApiCursor(many=[{"unit": "unit-01", "points": Decimal("0.5")}]),
            FakeApiCursor(
                many=[
                    {
                        "id": 7,
                        "unit_code": "unit-01",
                        "question_slug": "soma",
                        "question_title": "Soma",
                        "round": 1,
                        "state": "passed",
                        "points": Decimal("0.5"),
                        "created_at": now,
                    }
                ]
            ),
            FakeApiCursor(
                many=[
                    {
                        "id": 70,
                        "assignment_id": 7,
                        "number": 1,
                        "status": "passed",
                        "tests_total": 3,
                        "tests_passed": 3,
                        "output": "3/3 testes passaram",
                        "code": "def soma(a, b):\n    return a + b\n",
                        "started_at": now,
                        "finished_at": now,
                    }
                ]
            ),
            # Second call: missing student
            FakeApiCursor(one=None),
        ]
    )

    resp = client.get(
        "/api/students/20240001",
        basic_auth=("admin@unicode.local", "secret-password"),
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["student"]["registration"] == "20240001"
    assert payload["total_points"] == 0.5
    assert len(payload["assignments"]) == 1
    assert payload["assignments"][0]["attempts"][0]["code"].startswith("def soma")

    resp_404 = client.get(
        "/api/students/99999999",
        basic_auth=("admin@unicode.local", "secret-password"),
    )
    assert resp_404.status_code == 404
    assert "99999999" in resp_404.json()["detail"]


def test_api_unit_detail_returns_200_and_404_when_missing() -> None:
    client, _ = _make_client(
        [
            FakeApiCursor(one={"id": 1, "code": "unit-01", "title": "Unidade 1"}),
            FakeApiCursor(
                many=[
                    {
                        "slug": "soma",
                        "title": "Soma",
                        "active": True,
                        "assigned_count": 10,
                        "passed_count": 8,
                        "exhausted_count": 1,
                        "pending_count": 1,
                        "avg_attempts": Decimal("1.40"),
                    }
                ]
            ),
            # Second call: missing unit
            FakeApiCursor(one=None),
        ]
    )

    resp = client.get(
        "/api/units/unit-01",
        basic_auth=("admin@unicode.local", "secret-password"),
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["code"] == "unit-01"
    assert len(payload["questions"]) == 1
    assert payload["questions"][0]["pass_rate"] == 80.0

    resp_404 = client.get(
        "/api/units/unit-99",
        basic_auth=("admin@unicode.local", "secret-password"),
    )
    assert resp_404.status_code == 404
    assert "unit-99" in resp_404.json()["detail"]


def test_api_export_csv_returns_attachment_and_404_when_unit_missing() -> None:
    client, _ = _make_client(
        [
            FakeApiCursor(one={"id": 1, "code": "unit-01"}),
            FakeApiCursor(
                many=[
                    {
                        "registration": "20240001",
                        "email": "ana@edu.br",
                        "name": "Ana",
                        "class_group": "T01",
                        "points": Decimal("1.0"),
                    }
                ]
            ),
            # Second call: missing unit
            FakeApiCursor(one=None),
        ]
    )

    resp = client.get(
        "/api/export.csv?unit=unit-01",
        basic_auth=("admin@unicode.local", "secret-password"),
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert resp.headers["content-disposition"] == 'attachment; filename="notas-unit-01.csv"'
    lines = resp.text.strip().splitlines()
    assert lines[0] == "matricula,email,nome,turma,unidade,pontos"
    assert lines[1] == "20240001,ana@edu.br,Ana,T01,unit-01,1.0"

    resp_404 = client.get(
        "/api/export.csv?unit=unit-99",
        basic_auth=("admin@unicode.local", "secret-password"),
    )
    assert resp_404.status_code == 404


def test_spa_serving_fallback_503_and_unknown_api_404(tmp_path: Path) -> None:
    # 1. When dist dir does not exist -> 503
    client_no_dist, _ = _make_client(settings=_make_settings(tmp_path))
    resp_503 = client_no_dist.get("/alunos")
    assert resp_503.status_code == 503
    assert "Frontend React não compilado" in resp_503.text

    # 2. Unknown /api/* route -> 404
    resp_api_404 = client_no_dist.get("/api/unknown")
    assert resp_api_404.status_code == 404

    # 3. Create dist directory with index.html and assets/app.js
    dist_dir = tmp_path / "dist"
    assets_dir = dist_dir / "assets"
    assets_dir.mkdir(parents=True)
    (dist_dir / "index.html").write_text("<html><body>SPA</body></html>", encoding="utf-8")
    (assets_dir / "app.js").write_text("console.log('unicode');", encoding="utf-8")

    client_with_dist, _ = _make_client(settings=_make_settings(tmp_path))

    # Static asset served directly
    resp_asset = client_with_dist.get("/assets/app.js")
    assert resp_asset.status_code == 200
    assert "console.log('unicode');" in resp_asset.text

    # Client-side route falls back to index.html
    resp_spa = client_with_dist.get("/alunos")
    assert resp_spa.status_code == 200
    assert "<html><body>SPA</body></html>" in resp_spa.text


def test_cli_web_invokes_uvicorn_run(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, Any] = {}

    def fake_uvicorn_run(app: Any, *, host: str, port: int) -> None:
        called["app"] = app
        called["host"] = host
        called["port"] = port

    monkeypatch.setattr("unicode.cli_web.uvicorn.run", fake_uvicorn_run)
    runner = CliRunner()
    result = runner.invoke(cli_web_app, ["--host", "0.0.0.0", "--port", "9000"])
    assert result.exit_code == 0
    assert called["host"] == "0.0.0.0"
    assert called["port"] == 9000
    assert called["app"].title == "UniCode - Painel do Professor"
