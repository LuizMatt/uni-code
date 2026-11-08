import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from psycopg import errors

from unicode.models.student import ImportReport, Student
from unicode.services.students import (
    CsvFormatError,
    StudentConflictError,
    StudentNotFoundError,
    create_student,
    delete_class_group,
    delete_student,
    import_students_from_csv_bytes,
    update_student,
)


def _make_mock_conn() -> MagicMock:
    conn = MagicMock()
    conn.transaction.return_value.__enter__.return_value = conn
    conn.transaction.return_value.__exit__.return_value = False
    return conn


# --- create_student tests ---


def test_create_student_success() -> None:
    conn = _make_mock_conn()
    now = datetime.now(UTC)

    # 1. check registration -> not found
    # 2. check email -> not found
    # 3. insert student -> return row
    # 4. insert audit_log
    cursor_reg = MagicMock()
    cursor_reg.fetchone.return_value = None

    cursor_email = MagicMock()
    cursor_email.fetchone.return_value = None

    cursor_insert = MagicMock()
    cursor_insert.fetchone.return_value = {
        "registration": "12345",
        "email": "test@uni.edu",
        "name": "Test Student",
        "class_group": "T01",
        "created_at": now,
    }

    cursor_audit = MagicMock()

    conn.execute.side_effect = [cursor_reg, cursor_email, cursor_insert, cursor_audit]

    student = create_student(
        conn,
        " 12345 ",
        "  TEST@UNI.EDU  ",
        "  Test Student  ",
        "  T01  ",
        actor="admin_user",
    )

    assert isinstance(student, Student)
    assert student.registration == "12345"
    assert student.email == "test@uni.edu"
    assert student.name == "Test Student"
    assert student.class_group == "T01"
    assert student.created_at == now

    # Verify SQL calls
    assert conn.execute.call_count == 4
    # Check registration check query
    assert "WHERE registration = %s" in conn.execute.call_args_list[0][0][0]
    assert conn.execute.call_args_list[0][0][1] == ("12345",)

    # Check email check query
    assert "WHERE email = %s" in conn.execute.call_args_list[1][0][0]
    assert conn.execute.call_args_list[1][0][1] == ("test@uni.edu",)

    # Check insert student
    assert "INSERT INTO students" in conn.execute.call_args_list[2][0][0]
    assert conn.execute.call_args_list[2][0][1] == ("12345", "test@uni.edu", "Test Student", "T01")

    # Check audit log insert
    audit_call = conn.execute.call_args_list[3]
    assert "INSERT INTO audit_log" in audit_call[0][0]
    actor, action, raw_details = audit_call[0][1]
    assert actor == "admin_user"
    assert action == "create_student"
    details = json.loads(raw_details)
    assert details["registration"] == "12345"
    assert details["email"] == "test@uni.edu"
    assert details["name"] == "Test Student"
    assert details["class_group"] == "T01"


def test_create_student_empty_registration() -> None:
    conn = _make_mock_conn()
    with pytest.raises(ValueError, match="matrícula não pode ser vazia"):
        create_student(conn, "   ", "valid@uni.edu")


def test_create_student_invalid_email() -> None:
    conn = _make_mock_conn()
    with pytest.raises(ValueError, match="email inválido"):
        create_student(conn, "12345", "not-an-email")

    with pytest.raises(ValueError, match="email inválido"):
        create_student(conn, "12345", "a@b")


def test_create_student_registration_conflict() -> None:
    conn = _make_mock_conn()
    cursor = MagicMock()
    cursor.fetchone.return_value = {"registration": "12345"}
    conn.execute.return_value = cursor

    with pytest.raises(StudentConflictError, match="matrícula '12345' já cadastrada"):
        create_student(conn, "12345", "new@uni.edu")


def test_create_student_email_conflict() -> None:
    conn = _make_mock_conn()
    cursor_reg = MagicMock()
    cursor_reg.fetchone.return_value = None
    cursor_email = MagicMock()
    cursor_email.fetchone.return_value = {"registration": "99999"}
    conn.execute.side_effect = [cursor_reg, cursor_email]

    with pytest.raises(StudentConflictError, match="email 'used@uni.edu' já cadastrado"):
        create_student(conn, "12345", "used@uni.edu")


def test_create_student_unique_violation_db() -> None:
    conn = _make_mock_conn()
    cursor_reg = MagicMock()
    cursor_reg.fetchone.return_value = None
    cursor_email = MagicMock()
    cursor_email.fetchone.return_value = None

    conn.execute.side_effect = [
        cursor_reg,
        cursor_email,
        errors.UniqueViolation("duplicate key"),
    ]

    with pytest.raises(StudentConflictError, match="conflito ao cadastrar aluno"):
        create_student(conn, "12345", "race@uni.edu")


# --- update_student tests ---


def test_update_student_success() -> None:
    conn = _make_mock_conn()
    now = datetime.now(UTC)

    cursor_existing = MagicMock()
    cursor_existing.fetchone.return_value = {
        "registration": "12345",
        "email": "old@uni.edu",
        "name": "Old Name",
        "class_group": "T01",
        "created_at": now,
    }

    cursor_conflict = MagicMock()
    cursor_conflict.fetchone.return_value = None

    cursor_update = MagicMock()
    cursor_update.fetchone.return_value = {
        "registration": "12345",
        "email": "new@uni.edu",
        "name": "New Name",
        "class_group": "T02",
        "created_at": now,
    }

    cursor_audit = MagicMock()
    conn.execute.side_effect = [cursor_existing, cursor_conflict, cursor_update, cursor_audit]

    updated = update_student(
        conn,
        " 12345 ",
        " NEW@UNI.EDU ",
        " New Name ",
        " T02 ",
        actor="editor",
    )

    assert updated.registration == "12345"
    assert updated.email == "new@uni.edu"
    assert updated.name == "New Name"
    assert updated.class_group == "T02"

    # Verify conflict check query checked other students
    conflict_query = conn.execute.call_args_list[1]
    assert "WHERE email = %s AND registration <> %s" in conflict_query[0][0]
    assert conflict_query[0][1] == ("new@uni.edu", "12345")

    # Verify audit log recorded previous state
    audit_call = conn.execute.call_args_list[3]
    actor, action, raw_details = audit_call[0][1]
    assert actor == "editor"
    assert action == "update_student"
    details = json.loads(raw_details)
    assert details["previous"]["email"] == "old@uni.edu"
    assert details["previous"]["name"] == "Old Name"
    assert details["previous"]["class_group"] == "T01"
    assert details["email"] == "new@uni.edu"


def test_update_student_not_found() -> None:
    conn = _make_mock_conn()
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    conn.execute.return_value = cursor

    with pytest.raises(StudentNotFoundError, match="aluno '12345' não encontrado"):
        update_student(conn, "12345", "any@uni.edu")


def test_update_student_email_conflict_with_another_student() -> None:
    conn = _make_mock_conn()
    cursor_existing = MagicMock()
    cursor_existing.fetchone.return_value = {
        "registration": "12345",
        "email": "my@uni.edu",
        "name": "My Name",
        "class_group": "T01",
        "created_at": datetime.now(UTC),
    }

    cursor_conflict = MagicMock()
    cursor_conflict.fetchone.return_value = {"registration": "99999"}
    conn.execute.side_effect = [cursor_existing, cursor_conflict]

    with pytest.raises(StudentConflictError, match="já pertence a outro aluno \\(99999\\)"):
        update_student(conn, "12345", "other@uni.edu")


def test_update_student_invalid_inputs() -> None:
    conn = _make_mock_conn()
    with pytest.raises(ValueError, match="matrícula não pode ser vazia"):
        update_student(conn, "", "valid@uni.edu")

    with pytest.raises(ValueError, match="email inválido"):
        update_student(conn, "12345", "not-an-email")


# --- delete_student tests ---


def test_delete_student_success_cascade_order() -> None:
    conn = _make_mock_conn()
    cursor_existing = MagicMock()
    cursor_existing.fetchone.return_value = {
        "registration": "12345",
        "email": "student@uni.edu",
        "name": "Student",
        "class_group": "T01",
    }
    conn.execute.return_value = cursor_existing

    res = delete_student(conn, " 12345 ", actor="admin_del")
    assert res is True

    # 1. SELECT students ... FOR UPDATE
    # 2. DELETE FROM attempts ...
    # 3. DELETE FROM assignments ...
    # 4. DELETE FROM sessions ...
    # 5. DELETE FROM students ...
    # 6. INSERT INTO audit_log
    assert conn.execute.call_count == 6
    queries = [c[0][0] for c in conn.execute.call_args_list]

    assert (
        "SELECT registration, email, name, class_group FROM students "
        "WHERE registration = %s FOR UPDATE"
    ) in queries[0]
    assert (
        "DELETE FROM attempts WHERE assignment_id IN "
        "(SELECT id FROM assignments WHERE student_registration = %s)"
    ) in queries[1]
    assert "DELETE FROM assignments WHERE student_registration = %s" in queries[2]
    assert "DELETE FROM sessions WHERE student_registration = %s" in queries[3]
    assert "DELETE FROM students WHERE registration = %s" in queries[4]
    assert "INSERT INTO audit_log" in queries[5]

    for i in range(1, 5):
        assert conn.execute.call_args_list[i][0][1] == ("12345",)

    audit_call = conn.execute.call_args_list[5]
    actor, action, raw_details = audit_call[0][1]
    assert actor == "admin_del"
    assert action == "delete_student"
    details = json.loads(raw_details)
    assert details["registration"] == "12345"


def test_delete_student_not_found() -> None:
    conn = _make_mock_conn()
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    conn.execute.return_value = cursor

    with pytest.raises(StudentNotFoundError, match="aluno '12345' não encontrado"):
        delete_student(conn, "12345")


def test_delete_student_empty_registration() -> None:
    conn = _make_mock_conn()
    with pytest.raises(StudentNotFoundError, match="matrícula não pode ser vazia"):
        delete_student(conn, "   ")


# --- delete_class_group tests ---


def test_delete_class_group_empty() -> None:
    conn = _make_mock_conn()
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    conn.execute.return_value = cursor

    deleted_count = delete_class_group(conn, "EMPTY_GROUP")
    assert deleted_count == 0
    # Only the initial SELECT was performed
    assert conn.execute.call_count == 1
    assert "WHERE class_group = %s FOR UPDATE" in conn.execute.call_args_list[0][0][0]


def test_delete_class_group_cascade_success() -> None:
    conn = _make_mock_conn()
    cursor_select = MagicMock()
    cursor_select.fetchall.return_value = [
        {"registration": "00101"},
        {"registration": "00102"},
        {"registration": "00103"},
    ]
    cursor_del = MagicMock()
    conn.execute.side_effect = [
        cursor_select,
        cursor_del,
        cursor_del,
        cursor_del,
        cursor_del,
        cursor_del,
    ]

    deleted_count = delete_class_group(conn, " T01 ", actor="coord")
    assert deleted_count == 3

    assert conn.execute.call_count == 6
    queries = [c[0][0] for c in conn.execute.call_args_list]

    assert "SELECT registration FROM students WHERE class_group = %s FOR UPDATE" in queries[0]
    assert conn.execute.call_args_list[0][0][1] == ("T01",)

    assert (
        "DELETE FROM attempts WHERE assignment_id IN "
        "(SELECT id FROM assignments WHERE student_registration = ANY(%s))"
    ) in queries[1]
    assert "DELETE FROM assignments WHERE student_registration = ANY(%s)" in queries[2]
    assert "DELETE FROM sessions WHERE student_registration = ANY(%s)" in queries[3]
    assert "DELETE FROM students WHERE registration = ANY(%s)" in queries[4]
    assert "INSERT INTO audit_log" in queries[5]

    regs = ["00101", "00102", "00103"]
    for i in range(1, 5):
        assert conn.execute.call_args_list[i][0][1] == (regs,)

    audit_call = conn.execute.call_args_list[5]
    actor, action, raw_details = audit_call[0][1]
    assert actor == "coord"
    assert action == "delete_class_group"
    details = json.loads(raw_details)
    assert details["class_group"] == "T01"
    assert details["count"] == 3
    assert details["registrations"] == regs


# --- import_students_from_csv_bytes tests ---


def test_import_students_from_csv_bytes_success() -> None:
    conn = _make_mock_conn()
    cursor_audit = MagicMock()
    conn.execute.return_value = cursor_audit

    csv_data = "\ufeffemail,matricula,nome,turma\nstudent@uni.edu,00100,Student,T01\n".encode(
        "utf-8"
    )

    # In mock, conn.execute needs fetchone for existing student check
    cursor_check = MagicMock()
    cursor_check.fetchone.return_value = None
    conn.execute.side_effect = [cursor_check, MagicMock(), cursor_audit]

    report = import_students_from_csv_bytes(
        conn,
        csv_data,
        "import.csv",
        actor="batch_importer",
    )

    assert isinstance(report, ImportReport)
    assert report.created == 1
    assert not report.has_errors


def test_import_students_from_csv_bytes_invalid_utf8() -> None:
    conn = _make_mock_conn()
    invalid_bytes = b"\x80\x81\x82\xff"

    with pytest.raises(CsvFormatError, match="falha ao decodificar arquivo CSV"):
        import_students_from_csv_bytes(conn, invalid_bytes, "broken.csv")


def test_import_students_from_csv_bytes_empty_csv() -> None:
    conn = _make_mock_conn()
    with pytest.raises(CsvFormatError, match="arquivo vazio"):
        import_students_from_csv_bytes(conn, b"", "empty.csv")
