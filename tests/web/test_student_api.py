import base64
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from urllib.parse import urlsplit

import pytest

from unicode.config import Settings
from unicode.db import DictConnection
from unicode.models.student import ImportReport, RowIssue, Student
from unicode.services.students import (
    CsvFormatError,
    StudentConflictError,
    StudentNotFoundError,
)
from unicode.web import create_app


class AsgiResponse:
    def __init__(self, status_code: int, headers: dict[str, str], body: bytes) -> None:
        self.status_code = status_code
        self.headers = headers
        self.content = body

    @property
    def text(self) -> str:
        return self.content.decode("utf-8")

    def json(self) -> Any:
        return json.loads(self.text)


class ExtendedAsgiTestClient:
    """In-memory ASGI 3.0 test client supporting GET, POST, PUT, DELETE, and multipart."""

    def __init__(self, app: Any) -> None:
        self.app = app

    def request(
        self,
        method: str,
        path: str,
        *,
        json_data: Any = None,
        file_upload: tuple[str, str, bytes] | None = None,  # (field_name, filename, bytes)
        headers: dict[str, str] | None = None,
        basic_auth: tuple[str, str] | None = None,
    ) -> AsgiResponse:
        import asyncio

        req_headers: dict[str, str] = {}
        if headers:
            for k, v in headers.items():
                req_headers[k.lower()] = v
        if basic_auth is not None:
            raw = f"{basic_auth[0]}:{basic_auth[1]}".encode()
            token = base64.b64encode(raw).decode("ascii")
            req_headers["authorization"] = f"Basic {token}"

        body_bytes = b""
        if json_data is not None:
            body_bytes = json.dumps(json_data).encode("utf-8")
            req_headers["content-type"] = "application/json"
        elif file_upload is not None:
            field_name, filename, content = file_upload
            boundary = "----WebKitFormBoundaryX99StudentApiTest"
            req_headers["content-type"] = f"multipart/form-data; boundary={boundary}"
            header_str = (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
                f"Content-Type: text/csv\r\n\r\n"
            )
            footer_str = f"\r\n--{boundary}--\r\n"
            body_bytes = header_str.encode("utf-8") + content + footer_str.encode("utf-8")

        req_headers["content-length"] = str(len(body_bytes))

        parts = urlsplit(path)
        raw_headers = [
            (k.encode("latin-1"), v.encode("latin-1")) for k, v in req_headers.items()
        ]

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method.upper(),
            "scheme": "http",
            "path": parts.path or "/",
            "raw_path": (parts.path or "/").encode("ascii"),
            "query_string": parts.query.encode("ascii"),
            "headers": raw_headers,
            "client": ("127.0.0.1", 50000),
            "server": ("testserver", 80),
        }

        status_code = 500
        resp_headers: dict[str, str] = {}
        body_chunks: list[bytes] = []
        response_complete = asyncio.Event()
        request_sent = False

        async def receive() -> dict[str, Any]:
            nonlocal request_sent
            if not request_sent:
                request_sent = True
                return {"type": "http.request", "body": body_bytes, "more_body": False}
            await response_complete.wait()
            return {"type": "http.disconnect"}

        async def send(message: dict[str, Any]) -> None:
            nonlocal status_code, resp_headers
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                resp_headers = {
                    k.decode("latin-1").lower(): v.decode("latin-1")
                    for k, v in message.get("headers", [])
                }
            elif message["type"] == "http.response.body":
                body_chunks.append(message.get("body", b""))
                if not message.get("more_body", False):
                    response_complete.set()

        asyncio.run(self.app(scope, receive, send))
        return AsgiResponse(status_code, resp_headers, b"".join(body_chunks))

    def get(self, path: str, **kwargs: Any) -> AsgiResponse:
        return self.request("GET", path, **kwargs)

    def post(
        self,
        path: str,
        *,
        json: Any = None,
        file_upload: tuple[str, str, bytes] | None = None,
        **kwargs: Any,
    ) -> AsgiResponse:
        return self.request(
            "POST", path, json_data=json, file_upload=file_upload, **kwargs
        )

    def put(self, path: str, *, json: Any = None, **kwargs: Any) -> AsgiResponse:
        return self.request("PUT", path, json_data=json, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> AsgiResponse:
        return self.request("DELETE", path, **kwargs)


def _make_client(mock_conn: MagicMock | None = None) -> tuple[ExtendedAsgiTestClient, MagicMock]:
    conn = mock_conn or MagicMock()

    @contextmanager
    def conn_factory() -> Iterator[DictConnection]:
        yield conn

    settings = Settings(
        admin_email="admin@unicode.local",
        admin_password="secret-password",
        web_dist_dir=Path("nonexistent-dist"),
    )
    app = create_app(settings=settings, conn_factory=conn_factory)
    return ExtendedAsgiTestClient(app), conn


AUTH = ("admin@unicode.local", "secret-password")


# --- Authentication tests ---


def test_student_endpoints_require_admin_auth() -> None:
    client, _ = _make_client()

    resp_post = client.post("/api/students", json={"registration": "1", "email": "a@b.com"})
    assert resp_post.status_code == 401
    assert resp_post.json() == {"detail": "Credenciais inválidas."}

    resp_put = client.put("/api/students/1", json={"email": "a@b.com"})
    assert resp_put.status_code == 401

    resp_del = client.delete("/api/students/1")
    assert resp_del.status_code == 401

    resp_del_class = client.delete("/api/students/classes/T01")
    assert resp_del_class.status_code == 401

    resp_import = client.post(
        "/api/students/import-csv",
        file_upload=("file", "test.csv", b"matricula,email\n1,a@b.com"),
    )
    assert resp_import.status_code == 401


# --- POST /api/students tests ---


def test_create_student_success(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _make_client()
    now = datetime.now(UTC)

    def fake_create_student(
        conn: Any,
        registration: str,
        email: str,
        name: str | None = None,
        class_group: str | None = None,
        *,
        actor: str = "admin",
    ) -> Student:
        assert registration == "20240001"
        assert email == "ana@edu.br"
        assert name == "Ana Silva"
        assert class_group == "T01"
        assert actor == "admin@unicode.local"
        return Student(
            registration=registration,
            email=email,
            name=name,
            class_group=class_group,
            created_at=now,
        )

    monkeypatch.setattr("unicode.web.app.create_student", fake_create_student)

    resp = client.post(
        "/api/students",
        json={
            "registration": "20240001",
            "email": "ana@edu.br",
            "name": "Ana Silva",
            "class_group": "T01",
        },
        basic_auth=AUTH,
    )
    assert resp.status_code == 201
    assert resp.json() == {
        "registration": "20240001",
        "email": "ana@edu.br",
        "name": "Ana Silva",
        "class_group": "T01",
    }


def test_create_student_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _make_client()

    def fake_create_student(*args: Any, **kwargs: Any) -> Student:
        raise StudentConflictError("matrícula '20240001' já cadastrada")

    monkeypatch.setattr("unicode.web.app.create_student", fake_create_student)

    resp = client.post(
        "/api/students",
        json={"registration": "20240001", "email": "ana@edu.br"},
        basic_auth=AUTH,
    )
    assert resp.status_code == 409
    assert resp.json() == {"detail": "matrícula '20240001' já cadastrada"}


def test_create_student_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _make_client()

    def fake_create_student(*args: Any, **kwargs: Any) -> Student:
        raise ValueError("email inválido")

    monkeypatch.setattr("unicode.web.app.create_student", fake_create_student)

    resp = client.post(
        "/api/students",
        json={"registration": "20240001", "email": "invalid-email"},
        basic_auth=AUTH,
    )
    assert resp.status_code == 400
    assert resp.json() == {"detail": "email inválido"}


# --- PUT /api/students/{registration} tests ---


def test_update_student_success(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _make_client()
    now = datetime.now(UTC)

    def fake_update_student(
        conn: Any,
        registration: str,
        email: str,
        name: str | None = None,
        class_group: str | None = None,
        *,
        actor: str = "admin",
    ) -> Student:
        assert registration == "20240001"
        assert email == "ana_new@edu.br"
        assert name == "Ana Nova"
        assert class_group == "T02"
        assert actor == "admin@unicode.local"
        return Student(
            registration=registration,
            email=email,
            name=name,
            class_group=class_group,
            created_at=now,
        )

    monkeypatch.setattr("unicode.web.app.update_student", fake_update_student)

    resp = client.put(
        "/api/students/20240001",
        json={
            "email": "ana_new@edu.br",
            "name": "Ana Nova",
            "class_group": "T02",
        },
        basic_auth=AUTH,
    )
    assert resp.status_code == 200
    assert resp.json() == {
        "registration": "20240001",
        "email": "ana_new@edu.br",
        "name": "Ana Nova",
        "class_group": "T02",
    }


def test_update_student_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _make_client()

    def fake_update_student(*args: Any, **kwargs: Any) -> Student:
        raise StudentNotFoundError("aluno '999999' não encontrado")

    monkeypatch.setattr("unicode.web.app.update_student", fake_update_student)

    resp = client.put(
        "/api/students/999999",
        json={"email": "ana@edu.br"},
        basic_auth=AUTH,
    )
    assert resp.status_code == 404
    assert resp.json() == {"detail": "aluno '999999' não encontrado"}


def test_update_student_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _make_client()

    def fake_update_student(*args: Any, **kwargs: Any) -> Student:
        raise StudentConflictError("email 'used@edu.br' já pertence a outro aluno (20240002)")

    monkeypatch.setattr("unicode.web.app.update_student", fake_update_student)

    resp = client.put(
        "/api/students/20240001",
        json={"email": "used@edu.br"},
        basic_auth=AUTH,
    )
    assert resp.status_code == 409
    assert resp.json() == {"detail": "email 'used@edu.br' já pertence a outro aluno (20240002)"}


def test_update_student_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _make_client()

    def fake_update_student(*args: Any, **kwargs: Any) -> Student:
        raise ValueError("email inválido")

    monkeypatch.setattr("unicode.web.app.update_student", fake_update_student)

    resp = client.put(
        "/api/students/20240001",
        json={"email": "invalid-email"},
        basic_auth=AUTH,
    )
    assert resp.status_code == 400
    assert resp.json() == {"detail": "email inválido"}


# --- DELETE /api/students/{registration} tests ---


def test_delete_student_success(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _make_client()

    def fake_delete_student(
        conn: Any,
        registration: str,
        *,
        actor: str = "admin",
    ) -> bool:
        assert registration == "20240001"
        assert actor == "admin@unicode.local"
        return True

    monkeypatch.setattr("unicode.web.app.delete_student", fake_delete_student)

    resp = client.delete(
        "/api/students/20240001",
        basic_auth=AUTH,
    )
    assert resp.status_code == 200
    assert resp.json() == {"deleted": True, "registration": "20240001"}


def test_delete_student_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _make_client()

    def fake_delete_student(*args: Any, **kwargs: Any) -> bool:
        raise StudentNotFoundError("aluno '999999' não encontrado")

    monkeypatch.setattr("unicode.web.app.delete_student", fake_delete_student)

    resp = client.delete(
        "/api/students/999999",
        basic_auth=AUTH,
    )
    assert resp.status_code == 404
    assert resp.json() == {"detail": "aluno '999999' não encontrado"}


# --- DELETE /api/students/classes/{class_group} tests ---


def test_delete_class_group_success(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _make_client()

    def fake_delete_class_group(
        conn: Any,
        class_group: str,
        *,
        actor: str = "admin",
    ) -> int:
        assert class_group == "T01"
        assert actor == "admin@unicode.local"
        return 5

    monkeypatch.setattr("unicode.web.app.delete_class_group", fake_delete_class_group)

    resp = client.delete(
        "/api/students/classes/T01",
        basic_auth=AUTH,
    )
    assert resp.status_code == 200
    assert resp.json() == {"deleted": True, "class_group": "T01", "count": 5}


def test_delete_class_group_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _make_client()

    def fake_delete_class_group(*args: Any, **kwargs: Any) -> int:
        return 0

    monkeypatch.setattr("unicode.web.app.delete_class_group", fake_delete_class_group)

    resp = client.delete(
        "/api/students/classes/TURMA_INEXISTENTE",
        basic_auth=AUTH,
    )
    assert resp.status_code == 404
    assert resp.json() == {
        "detail": "Turma 'TURMA_INEXISTENTE' não encontrada ou sem alunos."
    }


# --- POST /api/students/import-csv tests ---


def test_import_students_csv_success(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _make_client()

    def fake_import_students_from_csv_bytes(
        conn: Any,
        content: bytes,
        filename: str,
        *,
        actor: str = "admin",
    ) -> ImportReport:
        assert b"20240001" in content
        assert filename == "turma-a.csv"
        assert actor == "admin@unicode.local"
        return ImportReport(
            created=10,
            updated=2,
            unchanged=1,
            issues=[
                RowIssue(line_number=3, message="linha duplicada", kind="warning"),
                RowIssue(line_number=5, message="email inválido", kind="error"),
            ],
        )

    monkeypatch.setattr(
        "unicode.web.app.import_students_from_csv_bytes",
        fake_import_students_from_csv_bytes,
    )

    csv_data = b"matricula,email,nome,turma\n20240001,ana@edu.br,Ana,T01\n"
    resp = client.post(
        "/api/students/import-csv",
        file_upload=("file", "turma-a.csv", csv_data),
        basic_auth=AUTH,
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["created"] == 10
    assert payload["updated"] == 2
    assert payload["unchanged"] == 1
    assert payload["has_errors"] is True
    assert payload["errors"] == [{"line_number": 5, "message": "email inválido"}]
    assert payload["warnings"] == [{"line_number": 3, "message": "linha duplicada"}]


def test_import_students_csv_format_error(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _make_client()

    def fake_import_students_from_csv_bytes(*args: Any, **kwargs: Any) -> ImportReport:
        raise CsvFormatError("arquivo vazio")

    monkeypatch.setattr(
        "unicode.web.app.import_students_from_csv_bytes",
        fake_import_students_from_csv_bytes,
    )

    resp = client.post(
        "/api/students/import-csv",
        file_upload=("file", "empty.csv", b""),
        basic_auth=AUTH,
    )
    assert resp.status_code == 400
    assert resp.json() == {"detail": "arquivo vazio"}
