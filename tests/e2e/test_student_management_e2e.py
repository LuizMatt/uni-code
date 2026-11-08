from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from tests.web.test_student_api import ExtendedAsgiTestClient
from unicode.config import Settings
from unicode.db import DictConnection
from unicode.models.student import ImportReport, Student
from unicode.web import create_app


def _make_e2e_client(mock_service_map: dict[str, Any]) -> ExtendedAsgiTestClient:
    fake_conn = MagicMock(spec=DictConnection)

    @contextmanager
    def conn_factory() -> Iterator[DictConnection]:
        yield fake_conn

    settings = Settings(
        admin_email="admin@unicode.local",
        admin_password="secret-password",
    )
    app = create_app(settings=settings, conn_factory=conn_factory)
    return ExtendedAsgiTestClient(app)


def test_full_student_management_lifecycle_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies end-to-end management lifecycle: add, update, csv import, and delete."""
    in_memory_db: dict[str, dict[str, Any]] = {}

    def mock_create_student(
        conn: Any,
        registration: str,
        email: str,
        name: str | None = None,
        class_group: str | None = None,
        *,
        actor: str = "admin",
    ) -> Student:
        if registration in in_memory_db:
            from unicode.services.students import StudentConflictError
            raise StudentConflictError(f"Matrícula {registration} já existe")
        st = Student(
            registration=registration,
            email=email,
            name=name,
            class_group=class_group,
            created_at=datetime.now(UTC),
        )
        in_memory_db[registration] = {
            "registration": st.registration,
            "email": st.email,
            "name": st.name,
            "class_group": st.class_group,
            "created_at": st.created_at,
        }
        return st

    def mock_update_student(
        conn: Any,
        registration: str,
        email: str,
        name: str | None = None,
        class_group: str | None = None,
        *,
        actor: str = "admin",
    ) -> Student:
        if registration not in in_memory_db:
            from unicode.services.students import StudentNotFoundError
            raise StudentNotFoundError("Aluno não encontrado")
        item = in_memory_db[registration]
        item["email"] = email
        item["name"] = name
        item["class_group"] = class_group
        return Student(
            registration=str(item["registration"]),
            email=str(item["email"]),
            name=str(item["name"]) if item["name"] is not None else None,
            class_group=str(item["class_group"]) if item["class_group"] is not None else None,
            created_at=item["created_at"],
        )

    def mock_delete_student(conn: Any, registration: str, *, actor: str = "admin") -> bool:
        if registration not in in_memory_db:
            from unicode.services.students import StudentNotFoundError
            raise StudentNotFoundError("Aluno não encontrado")
        del in_memory_db[registration]
        return True

    def mock_delete_class_group(conn: Any, class_group: str, *, actor: str = "admin") -> int:
        matching = [r for r, s in in_memory_db.items() if s.get("class_group") == class_group]
        for r in matching:
            del in_memory_db[r]
        return len(matching)

    def mock_import_students_csv(
        conn: Any, content: bytes, filename: str, *, actor: str = "admin"
    ) -> ImportReport:
        lines = content.decode("utf-8-sig").splitlines()[1:]
        created = 0
        for line in lines:
            if not line.strip():
                continue
            parts = line.split(",")
            email, reg, name, turma = parts[0], parts[1], parts[2], parts[3]
            in_memory_db[reg] = {
                "registration": reg,
                "email": email,
                "name": name,
                "class_group": turma,
                "created_at": datetime.now(UTC),
            }
            created += 1
        return ImportReport(created=created, updated=0, unchanged=0)

    monkeypatch.setattr("unicode.web.app.create_student", mock_create_student)
    monkeypatch.setattr("unicode.web.app.update_student", mock_update_student)
    monkeypatch.setattr("unicode.web.app.delete_student", mock_delete_student)
    monkeypatch.setattr("unicode.web.app.delete_class_group", mock_delete_class_group)
    monkeypatch.setattr("unicode.web.app.import_students_from_csv_bytes", mock_import_students_csv)

    client = _make_e2e_client({})
    auth = ("admin@unicode.local", "secret-password")

    # 1. Create a student via POST
    res_create = client.request(
        "POST",
        "/api/students",
        basic_auth=auth,
        json_data={
            "registration": "2026001",
            "email": "aluno1@test.com",
            "name": "Aluno Teste",
            "class_group": "T01",
        },
    )
    assert res_create.status_code == 201
    assert res_create.json()["registration"] == "2026001"
    assert "2026001" in in_memory_db

    # 2. Update the student via PUT
    res_update = client.request(
        "PUT",
        "/api/students/2026001",
        basic_auth=auth,
        json_data={
            "email": "aluno1_novo@test.com",
            "name": "Aluno Renomeado",
            "class_group": "T01",
        },
    )
    assert res_update.status_code == 200
    assert in_memory_db["2026001"]["name"] == "Aluno Renomeado"

    # 3. Import CSV with 2 additional students
    csv_data = (
        b"email,matricula,nome,turma\n"
        b"a2@test.com,2026002,Aluno 2,T01\n"
        b"a3@test.com,2026003,Aluno 3,T02\n"
    )
    res_csv = client.request(
        "POST",
        "/api/students/import-csv",
        basic_auth=auth,
        file_upload=("file", "turma.csv", csv_data),
    )
    assert res_csv.status_code == 200
    assert res_csv.json()["created"] == 2
    assert len(in_memory_db) == 3

    # 4. Delete one student via DELETE
    res_del_single = client.request(
        "DELETE",
        "/api/students/2026003",
        basic_auth=auth,
    )
    assert res_del_single.status_code == 200
    assert "2026003" not in in_memory_db
    assert len(in_memory_db) == 2

    # 5. Delete entire class T01
    res_del_class = client.request(
        "DELETE",
        "/api/students/classes/T01",
        basic_auth=auth,
    )
    assert res_del_class.status_code == 200
    assert res_del_class.json()["count"] == 2
    assert len(in_memory_db) == 0
