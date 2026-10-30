from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from unicode.cli_admin import app, format_reset_report
from unicode.models.assignment import Assignment, ResetResult
from unicode.services.assignments import NoActiveAssignmentsError, StudentNotFoundError

runner = CliRunner()


def _sample_assignment(slug: str, round_num: int) -> Assignment:
    return Assignment(
        id=1,
        student_registration="2026001",
        unit_id=1,
        unit_code="unit-01",
        question_id=1,
        question_slug=slug,
        round=round_num,
        state="pending",
        points=Decimal("0.0"),
        created_at=datetime.now(UTC),
    )


def test_format_reset_report_with_and_without_reuse_warning() -> None:
    res = ResetResult(
        student_registration="2026001",
        unit_code="unit-01",
        new_round=2,
        replaced_assignments=[
            _sample_assignment("par-ou-impar", 1),
            _sample_assignment("soma-dois-numeros", 1),
        ],
        new_assignments=[
            _sample_assignment("fatorial", 2),
            _sample_assignment("inverter-string", 2),
        ],
        reused_questions=False,
    )
    out = format_reset_report(res)
    assert "Reset de sorteio para 2026001 (unit-01) - rodada 2" in out
    assert "  substituídas: par-ou-impar, soma-dois-numeros" in out
    assert "  novas:        fatorial, inverter-string" in out
    assert "Avisos:" not in out

    res_reused = ResetResult(
        student_registration="2026001",
        unit_code="unit-01",
        new_round=3,
        replaced_assignments=[_sample_assignment("fatorial", 2)],
        new_assignments=[_sample_assignment("par-ou-impar", 3)],
        reused_questions=True,
    )
    out_reused = format_reset_report(res_reused)
    assert "Avisos:" in out_reused
    assert "questões de rodadas anteriores foram reaproveitadas" in out_reused


def test_cli_reset_success_mocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("UNICODE_QUESTIONS_DIR", str(tmp_path / "questions"))
    monkeypatch.setenv("UNICODE_WORKSPACES_DIR", str(tmp_path / "workspaces"))

    mock_result = ResetResult(
        student_registration="2026001",
        unit_code="unit-01",
        new_round=2,
        replaced_assignments=[_sample_assignment("q01", 1)],
        new_assignments=[_sample_assignment("q02", 2)],
        reused_questions=False,
    )
    with (
        patch("unicode.cli_admin.transaction") as mock_tx,
        patch("unicode.cli_admin.reset_assignments", return_value=mock_result) as mock_reset,
        patch("unicode.cli_admin.archive_replaced_workspaces") as mock_archive,
        patch("unicode.cli_admin.provision_workspace") as mock_provision,
    ):
        mock_conn = MagicMock()
        mock_tx.return_value.__enter__.return_value = mock_conn

        result = runner.invoke(
            app,
            ["reset", "2026001", "--unidade", "unit-01", "--questao", "q01"],
        )
        assert result.exit_code == 0
        assert "Reset de sorteio para 2026001 (unit-01) - rodada 2" in result.output
        mock_reset.assert_called_once_with(
            mock_conn,
            "2026001",
            "unit-01",
            question_slug="q01",
        )
        assert mock_archive.called
        assert mock_provision.called


def test_cli_reset_domain_error_returns_exit_code_1() -> None:
    with (
        patch("unicode.cli_admin.transaction") as mock_tx,
        patch(
            "unicode.cli_admin.reset_assignments",
            side_effect=StudentNotFoundError("aluno '999' não encontrado"),
        ),
    ):
        mock_tx.return_value.__enter__.return_value = MagicMock()
        result = runner.invoke(app, ["reset", "999", "--unidade", "unit-01"])
        assert result.exit_code == 1
        assert "Erro: aluno '999' não encontrado" in result.output


def test_cli_reset_no_active_assignments_returns_exit_code_1() -> None:
    with (
        patch("unicode.cli_admin.transaction") as mock_tx,
        patch(
            "unicode.cli_admin.reset_assignments",
            side_effect=NoActiveAssignmentsError("sem sorteio ativo"),
        ),
    ):
        mock_tx.return_value.__enter__.return_value = MagicMock()
        result = runner.invoke(app, ["reset", "2026001", "--unidade", "unit-01"])
        assert result.exit_code == 1
        assert "Erro: sem sorteio ativo" in result.output


def test_cli_reset_db_error_returns_exit_code_2() -> None:
    with patch("unicode.cli_admin.transaction", side_effect=RuntimeError("db failed")):
        result = runner.invoke(app, ["reset", "2026001", "--unidade", "unit-01"])
        assert result.exit_code == 2
        assert "Erro fatal de banco de dados: db failed" in result.output


def test_cli_reset_workspace_error_returns_exit_code_2() -> None:
    mock_result = ResetResult(
        student_registration="2026001",
        unit_code="unit-01",
        new_round=2,
        replaced_assignments=[_sample_assignment("q01", 1)],
        new_assignments=[_sample_assignment("q02", 2)],
        reused_questions=False,
    )
    with (
        patch("unicode.cli_admin.transaction") as mock_tx,
        patch("unicode.cli_admin.reset_assignments", return_value=mock_result),
        patch(
            "unicode.cli_admin.archive_replaced_workspaces",
            side_effect=OSError("disk failure"),
        ),
    ):
        mock_tx.return_value.__enter__.return_value = MagicMock()
        result = runner.invoke(app, ["reset", "2026001", "--unidade", "unit-01"])
        assert result.exit_code == 2
        assert "Erro fatal ao atualizar workspace: disk failure" in result.output
