from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

import unicode.cli_admin as cli_admin_mod
from unicode.cli_admin import app
from unicode.models.grade import StudentUnitGrade
from unicode.services.grades import GradeReportError

runner = CliRunner()


def test_export_notas_prints_csv_to_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    @contextmanager
    def fake_tx() -> Iterator[Any]:
        yield object()

    monkeypatch.setattr(cli_admin_mod, "transaction", fake_tx)
    monkeypatch.setattr(cli_admin_mod, "close_pool", lambda: None)
    monkeypatch.setattr(
        cli_admin_mod,
        "list_unit_grades_for_export",
        lambda conn, unit_code, class_group=None: [
            StudentUnitGrade(
                registration="20240001",
                email="ana@edu.br",
                name="Ana",
                class_group="T01",
                unit_code=unit_code,
                points=0.5,
            )
        ],
    )

    result = runner.invoke(app, ["export-notas", "unit-01"])
    assert result.exit_code == 0
    assert "matricula,email,nome,turma,unidade,pontos" in result.stdout
    assert "20240001,ana@edu.br,Ana,T01,unit-01,0.5" in result.stdout


def test_export_notas_writes_file_when_output_specified(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    @contextmanager
    def fake_tx() -> Iterator[Any]:
        yield object()

    monkeypatch.setattr(cli_admin_mod, "transaction", fake_tx)
    monkeypatch.setattr(cli_admin_mod, "close_pool", lambda: None)
    monkeypatch.setattr(
        cli_admin_mod,
        "list_unit_grades_for_export",
        lambda conn, unit_code, class_group=None: [
            StudentUnitGrade(
                registration="20240001",
                email="ana@edu.br",
                name="Ana",
                class_group="T01",
                unit_code=unit_code,
                points=1.0,
            )
        ],
    )

    out_file = tmp_path / "notas.csv"
    result = runner.invoke(app, ["export-notas", "unit-01", "--output", str(out_file)])
    assert result.exit_code == 0
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "20240001,ana@edu.br,Ana,T01,unit-01,1.0" in content


def test_export_notas_exits_1_on_grade_report_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @contextmanager
    def fake_tx() -> Iterator[Any]:
        yield object()

    def raise_grade_error(
        conn: Any, unit_code: str, class_group: str | None = None
    ) -> list[StudentUnitGrade]:
        raise GradeReportError(f"Unidade '{unit_code}' não encontrada.")

    monkeypatch.setattr(cli_admin_mod, "transaction", fake_tx)
    monkeypatch.setattr(cli_admin_mod, "close_pool", lambda: None)
    monkeypatch.setattr(cli_admin_mod, "list_unit_grades_for_export", raise_grade_error)

    result = runner.invoke(app, ["export-notas", "unit-99"])
    assert result.exit_code == 1
    assert "Unidade 'unit-99' não encontrada." in (result.stdout + result.stderr)


def test_export_notas_exits_2_on_database_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @contextmanager
    def failing_tx() -> Iterator[Any]:
        raise RuntimeError("connection refused")
        yield

    monkeypatch.setattr(cli_admin_mod, "transaction", failing_tx)
    monkeypatch.setattr(cli_admin_mod, "close_pool", lambda: None)

    result = runner.invoke(app, ["export-notas", "unit-01"])
    assert result.exit_code == 2
    assert "Erro fatal de banco de dados" in (result.stdout + result.stderr)
