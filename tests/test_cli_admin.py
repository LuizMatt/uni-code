from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from typer.testing import CliRunner

from tests.support import TEST_DAEMON_URL, TEST_OWNER_URL
from unicode.cli_admin import app
from unicode.db import close_pool

runner = CliRunner()


@pytest.fixture
def clean_cli_db(
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
            conn.execute("DELETE FROM students WHERE registration IN ('00555', '00777')")
            conn.execute("DELETE FROM audit_log WHERE actor = 'admin'")


def test_cli_help() -> None:
    res = runner.invoke(app, ["--help"])
    assert res.exit_code == 0
    assert "import-alunos" in res.stdout
    assert "list-alunos" in res.stdout


def test_cli_import_file_not_found() -> None:
    res = runner.invoke(app, ["import-alunos", "non_existent_file.csv"])
    assert res.exit_code == 2


def test_cli_import_empty_file(tmp_path: Path) -> None:
    empty_csv = tmp_path / "empty.csv"
    empty_csv.write_text("", encoding="utf-8")
    res = runner.invoke(app, ["import-alunos", str(empty_csv)])
    assert res.exit_code == 2
    assert "arquivo vazio" in res.output


def test_cli_import_invalid_encoding(tmp_path: Path) -> None:
    bad_file = tmp_path / "bad.csv"
    bad_file.write_bytes(b"\xff\xfe\x00\x00")
    res = runner.invoke(app, ["import-alunos", str(bad_file)])
    assert res.exit_code == 2
    assert "não está codificado em UTF-8" in res.output


@pytest.mark.db
def test_cli_import_success_and_list(tmp_path: Path, clean_cli_db: None) -> None:
    valid_csv = tmp_path / "students.csv"
    valid_csv.write_text(
        "email,matricula,nome,turma\ncli@uni.edu,00555,Cli User,T01\n",
        encoding="utf-8",
    )

    res = runner.invoke(app, ["import-alunos", str(valid_csv)])
    assert res.exit_code == 0
    assert "criados:     1" in res.stdout

    res_list = runner.invoke(app, ["list-alunos", "--turma", "T01"])
    assert res_list.exit_code == 0
    assert "00555" in res_list.stdout
    assert "cli@uni.edu" in res_list.stdout


@pytest.mark.db
def test_cli_import_with_partial_errors(tmp_path: Path, clean_cli_db: None) -> None:
    partial_csv = tmp_path / "partial.csv"
    partial_csv.write_text(
        "email,matricula,nome,turma\nok@uni.edu,00777,Ok,T01\ninvalid_email,00888,Invalid,T01\n",
        encoding="utf-8",
    )

    res = runner.invoke(app, ["import-alunos", str(partial_csv)])
    assert res.exit_code == 1
    assert "criados:     1" in res.stdout
    assert "rejeitados:  1" in res.stdout
    assert "email inválido" in res.stdout
