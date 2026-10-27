from datetime import UTC, datetime

from unicode.models.student import (
    ImportReport,
    ParseResult,
    RowIssue,
    Student,
    StudentRow,
)


def test_student_row_creation() -> None:
    row = StudentRow(
        line_number=2,
        registration="00123",
        email="student@uni.edu",
        name="John Doe",
        class_group="T01",
    )
    assert row.registration == "00123"
    assert row.email == "student@uni.edu"
    assert row.name == "John Doe"
    assert row.class_group == "T01"


def test_row_issue_and_parse_result() -> None:
    issue = RowIssue(line_number=3, message="invalid email", kind="error")
    result = ParseResult(valid_rows=[], issues=[issue])
    assert len(result.issues) == 1
    assert result.issues[0].kind == "error"
    assert len(result.errors) == 1
    assert len(result.warnings) == 0


def test_import_report_properties() -> None:
    report = ImportReport(
        created=2,
        updated=1,
        unchanged=0,
        issues=[
            RowIssue(line_number=4, message="invalid email", kind="error"),
            RowIssue(line_number=5, message="duplicate row", kind="warning"),
        ],
    )
    assert report.total_processed == 3
    assert report.has_errors is True
    assert len(report.errors) == 1
    assert len(report.warnings) == 1


def test_student_dataclass() -> None:
    now = datetime.now(UTC)
    student = Student(
        registration="00123",
        email="student@uni.edu",
        name="John",
        class_group="T01",
        created_at=now,
    )
    assert student.registration == "00123"
    assert student.created_at == now
