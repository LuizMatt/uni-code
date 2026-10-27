from datetime import UTC, datetime

from unicode.cli_admin import format_import_report, format_student_list
from unicode.models.student import ImportReport, RowIssue, Student


def test_format_import_report_with_warnings_and_errors() -> None:
    report = ImportReport(
        created=2,
        updated=1,
        unchanged=0,
        issues=[
            RowIssue(
                line_number=7,
                message="linha idêntica à linha 4; considerada uma vez",
                kind="warning",
            ),
            RowIssue(line_number=5, message="email inválido", kind="error"),
        ],
    )
    output = format_import_report("students.csv", report)
    assert "Importação de students.csv" in output
    assert "criados:     2" in output
    assert "atualizados: 1" in output
    assert "sem mudança: 0" in output
    assert "rejeitados:  1" in output
    assert "Avisos:" in output
    assert "  linha 7: linha idêntica à linha 4" in output
    assert "Erros (linhas não importadas):" in output
    assert "  linha 5: email inválido" in output


def test_format_import_report_clean() -> None:
    report = ImportReport(created=5, updated=0, unchanged=0, issues=[])
    output = format_import_report("students.csv", report)
    assert "rejeitados:  0" in output
    assert "Avisos:" not in output
    assert "Erros" not in output


def test_format_student_list() -> None:
    now = datetime.now(UTC)
    students = [
        Student("00050", "c@uni.edu", "Alice", "T01", now),
        Student("00100", "a@uni.edu", None, None, now),
    ]
    output = format_student_list(students)
    assert "MATRÍCULA" in output
    assert "00050" in output
    assert "Alice" in output
    assert "-" in output
    assert "2 aluno(s)" in output


def test_format_student_list_empty() -> None:
    assert format_student_list([]) == "Nenhum aluno encontrado."
