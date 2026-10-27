import json

import pytest

from unicode.db import DictConnection
from unicode.services.students import import_students, parse_students_csv

pytestmark = pytest.mark.db


def test_import_students_create_and_audit(daemon_conn: DictConnection) -> None:
    csv_content = """email,matricula,nome,turma
student1@uni.edu,00101,Student One,T01
student2@uni.edu,00102,Student Two,T01
"""
    parsed = parse_students_csv(csv_content)
    report = import_students(daemon_conn, parsed, source="students.csv")

    assert report.created == 2
    assert report.updated == 0
    assert report.unchanged == 0
    assert not report.has_errors

    # Verify rows in DB
    sql_check = (
        "SELECT registration, email, name, class_group FROM students "
        "WHERE registration IN ('00101', '00102') ORDER BY registration"
    )
    rows = daemon_conn.execute(sql_check).fetchall()
    assert len(rows) == 2
    assert rows[0]["registration"] == "00101"
    assert rows[0]["email"] == "student1@uni.edu"

    # Verify audit_log
    audit = daemon_conn.execute(
        "SELECT actor, action, details FROM audit_log WHERE action = 'import_csv'"
    ).fetchone()
    assert audit is not None
    assert audit["actor"] == "admin"
    raw_details = audit["details"]
    details = raw_details if isinstance(raw_details, dict) else json.loads(raw_details)
    assert details["source"] == "students.csv"
    assert details["created"] == 2


def test_import_students_upsert_logic(daemon_conn: DictConnection) -> None:
    # Initial insert
    parsed1 = parse_students_csv("email,matricula,nome,turma\na@uni.edu,00100,Old Name,T01\n")
    import_students(daemon_conn, parsed1, source="init.csv")

    # Re-import with changed name, same email, empty turma (should keep T01)
    parsed2 = parse_students_csv("email,matricula,nome,turma\na@uni.edu,00100,New Name,\n")
    report2 = import_students(daemon_conn, parsed2, source="update.csv")
    assert report2.updated == 1
    assert report2.created == 0
    assert report2.unchanged == 0

    row = daemon_conn.execute("SELECT * FROM students WHERE registration = '00100'").fetchone()
    assert row is not None
    assert row["name"] == "New Name"
    assert row["class_group"] == "T01"

    # Re-import identical -> unchanged
    parsed3 = parse_students_csv("email,matricula,nome,turma\na@uni.edu,00100,New Name,T01\n")
    report3 = import_students(daemon_conn, parsed3, source="same.csv")
    assert report3.unchanged == 1
    assert report3.updated == 0


def test_import_students_email_conflict_with_another_student(daemon_conn: DictConnection) -> None:
    # Student 1 has email x@uni.edu
    parsed1 = parse_students_csv("email,matricula,nome,turma\nx@uni.edu,00101,One,T01\n")
    import_students(daemon_conn, parsed1, source="init.csv")

    # Student 2 tries to use x@uni.edu and Student 3 is valid
    csv_conflict = """email,matricula,nome,turma
x@uni.edu,00102,Two,T01
y@uni.edu,00103,Three,T01
"""
    parsed2 = parse_students_csv(csv_conflict)
    report2 = import_students(daemon_conn, parsed2, source="conflict.csv")

    assert report2.created == 1  # 00103 imported
    assert report2.has_errors
    assert any("email x@uni.edu já pertence a outra matrícula" in e.message for e in report2.errors)

    # Verify student 3 exists, student 2 does not
    has_00103 = daemon_conn.execute(
        "SELECT 1 FROM students WHERE registration = '00103'"
    ).fetchone()
    assert has_00103 is not None

    has_00102 = daemon_conn.execute(
        "SELECT 1 FROM students WHERE registration = '00102'"
    ).fetchone()
    assert has_00102 is None
