from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import psycopg
import pytest
from typer.testing import CliRunner

from tests.support import TEST_DAEMON_URL, TEST_OWNER_URL
from unicode.cli_admin import app, format_sync_report
from unicode.db import close_pool
from unicode.models.question import QuestionIssue, SyncReport

runner = CliRunner()


@pytest.fixture
def clean_cli_questions_db(
    database_available: None,
    migrated_db: None,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    monkeypatch.setenv("UNICODE_DATABASE_URL", TEST_DAEMON_URL)
    close_pool()
    try:
        yield
    finally:
        close_pool()
        with psycopg.connect(TEST_OWNER_URL) as conn:
            conn.execute("DELETE FROM questions WHERE slug = 'soma'")
            conn.execute("DELETE FROM units WHERE code = 'unit-01'")
            conn.execute("DELETE FROM audit_log WHERE action = 'sync_questions'")


def test_format_sync_report_full() -> None:
    report = SyncReport(
        units_created=1,
        units_updated=2,
        questions_created=3,
        questions_updated=4,
        questions_deactivated=5,
        issues=[
            QuestionIssue(path="u1", message="aviso 1", kind="warning"),
            QuestionIssue(path="u2", message="erro 1", kind="error"),
        ],
    )
    formatted = format_sync_report("questions", report)
    assert "Sincronização de questions" in formatted
    assert "unidades criadas:     1" in formatted
    assert "unidades atualizadas: 2" in formatted
    assert "questões criadas:     3" in formatted
    assert "questões atualizadas: 4" in formatted
    assert "questões desativadas: 5" in formatted
    assert "Avisos:" in formatted
    assert "  u1: aviso 1" in formatted
    assert "Erros (sincronização não efetuada):" in formatted
    assert "  u2: erro 1" in formatted


def test_cli_sync_questoes_dir_not_found() -> None:
    result = runner.invoke(app, ["sync-questoes", "--dir", "diretorio_inexistente_xyz"])
    assert result.exit_code == 2
    assert "Erro fatal: o diretório 'diretorio_inexistente_xyz' não existe." in result.output


def test_cli_sync_questoes_validation_error(tmp_path: Path) -> None:
    u_dir = tmp_path / "unit-01"
    u_dir.mkdir()
    result = runner.invoke(app, ["sync-questoes", "--dir", str(tmp_path)])
    assert result.exit_code == 1
    assert "Erros (sincronização não efetuada):" in result.output


def test_cli_sync_questoes_mocked_db_flow(tmp_path: Path) -> None:
    u_dir = tmp_path / "unit-01"
    u_dir.mkdir()
    (u_dir / "unit.yaml").write_text("code: unit-01\ntitle: U1\n", encoding="utf-8")
    q_dir = u_dir / "soma"
    q_dir.mkdir()
    (q_dir / "question.yaml").write_text("title: Soma\n", encoding="utf-8")
    (q_dir / "README.md").write_text("#\n", encoding="utf-8")
    (q_dir / "template.py").write_text("pass\n", encoding="utf-8")
    (q_dir / "test_eval.py").write_text("pass\n", encoding="utf-8")

    mock_report = SyncReport(units_created=1, questions_created=1)
    with (
        patch("unicode.cli_admin.transaction") as mock_tx,
        patch("unicode.cli_admin.sync_questions", return_value=mock_report) as mock_sync,
    ):
        mock_conn = MagicMock()
        mock_tx.return_value.__enter__.return_value = mock_conn

        result = runner.invoke(app, ["sync-questoes", "--dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "Sincronização de" in result.output
        assert "unidades criadas:     1" in result.output
        assert "questões criadas:     1" in result.output
        assert mock_sync.called


@pytest.mark.db
def test_cli_sync_questoes_success(tmp_path: Path, clean_cli_questions_db: None) -> None:
    u_dir = tmp_path / "unit-01"
    u_dir.mkdir()
    (u_dir / "unit.yaml").write_text("code: unit-01\ntitle: U1\n", encoding="utf-8")
    q_dir = u_dir / "soma"
    q_dir.mkdir()
    (q_dir / "question.yaml").write_text("title: Soma\n", encoding="utf-8")
    (q_dir / "README.md").write_text("#\n", encoding="utf-8")
    (q_dir / "template.py").write_text("pass\n", encoding="utf-8")
    (q_dir / "test_eval.py").write_text("pass\n", encoding="utf-8")

    result = runner.invoke(app, ["sync-questoes", "--dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "Sincronização de" in result.output
    assert "unidades criadas:" in result.output
    assert "questões criadas:" in result.output
