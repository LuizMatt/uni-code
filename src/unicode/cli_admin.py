from pathlib import Path
from typing import Annotated

import typer

from unicode.config import get_settings
from unicode.db import close_pool, transaction
from unicode.models.question import SyncReport
from unicode.models.student import ImportReport, Student
from unicode.services.questions import scan_and_validate_questions_dir, sync_questions
from unicode.services.students import (
    CsvFormatError,
    import_students,
    list_students,
    parse_students_csv,
)

app = typer.Typer(
    name="unicode-admin",
    help="UniCode - Ferramenta administrativa do professor.",
    add_completion=False,
)


def format_import_report(source: str, report: ImportReport) -> str:
    """Format the import report in human-readable Portuguese."""
    rejected_count = len(report.errors)
    lines = [
        f"Importação de {source}",
        f"  criados:     {report.created}",
        f"  atualizados: {report.updated}",
        f"  sem mudança: {report.unchanged}",
        f"  rejeitados:  {rejected_count}",
    ]

    if report.warnings:
        lines.append("\nAvisos:")
        for w in report.warnings:
            lines.append(f"  linha {w.line_number}: {w.message}")

    if report.errors:
        lines.append("\nErros (linhas não importadas):")
        for e in report.errors:
            lines.append(f"  linha {e.line_number}: {e.message}")

    return "\n".join(lines)


def format_student_list(students: list[Student]) -> str:
    """Format the student list in a tabular layout."""
    if not students:
        return "Nenhum aluno encontrado."

    headers = ("MATRÍCULA", "EMAIL", "NOME", "TURMA")
    rows: list[tuple[str, str, str, str]] = []
    for s in students:
        rows.append((s.registration, s.email, s.name or "-", s.class_group or "-"))

    # Calculate column widths
    col_widths = [len(h) for h in headers]
    for row in rows:
        for idx, val in enumerate(row):
            col_widths[idx] = max(col_widths[idx], len(val))

    fmt = (
        f"{{:<{col_widths[0]}}}  "
        f"{{:<{col_widths[1]}}}  "
        f"{{:<{col_widths[2]}}}  "
        f"{{:<{col_widths[3]}}}"
    )

    lines = [fmt.format(*headers)]
    for row in rows:
        lines.append(fmt.format(*row))

    lines.append(f"\n{len(students)} aluno(s)")
    return "\n".join(lines)


@app.command("import-alunos")
def import_alunos_cmd(
    caminho_csv: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            help="Caminho do arquivo CSV de alunos.",
        ),
    ],
) -> None:
    """Importa alunos a partir de um arquivo CSV UTF-8."""
    try:
        content_bytes = caminho_csv.read_bytes()
        text = content_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        typer.echo("Erro fatal: o arquivo não está codificado em UTF-8.", err=True)
        raise typer.Exit(code=2) from None
    except Exception as exc:
        typer.echo(f"Erro fatal ao ler o arquivo: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    try:
        parsed = parse_students_csv(text)
    except CsvFormatError as exc:
        typer.echo(f"Erro fatal no formato do CSV: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    try:
        with transaction() as conn:
            report = import_students(conn, parsed, source=caminho_csv.name)
    except Exception as exc:
        typer.echo(f"Erro fatal de banco de dados: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    finally:
        close_pool()

    typer.echo(format_import_report(caminho_csv.name, report))

    if report.has_errors:
        raise typer.Exit(code=1)


@app.command("list-alunos")
def list_alunos_cmd(
    turma: Annotated[
        str | None,
        typer.Option("--turma", "-t", help="Filtrar por código da turma."),
    ] = None,
) -> None:
    """Lista os alunos cadastrados no sistema."""
    try:
        with transaction() as conn:
            students = list_students(conn, class_group=turma)
    except Exception as exc:
        typer.echo(f"Erro fatal ao consultar o banco de dados: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    finally:
        close_pool()

    typer.echo(format_student_list(students))


def format_sync_report(target_dir: str, report: SyncReport) -> str:
    """Format the question synchronization report in human-readable Portuguese."""
    lines = [
        f"Sincronização de {target_dir}",
        f"  unidades criadas:     {report.units_created}",
        f"  unidades atualizadas: {report.units_updated}",
        f"  questões criadas:     {report.questions_created}",
        f"  questões atualizadas: {report.questions_updated}",
        f"  questões desativadas: {report.questions_deactivated}",
    ]
    if report.warnings:
        lines.append("\nAvisos:")
        for w in report.warnings:
            lines.append(f"  {w.path}: {w.message}")

    if report.errors:
        lines.append("\nErros (sincronização não efetuada):")
        for e in report.errors:
            lines.append(f"  {e.path}: {e.message}")

    return "\n".join(lines)


@app.command("sync-questoes")
def sync_questoes_cmd(
    caminho_dir: Annotated[
        Path | None,
        typer.Option("--dir", "-d", help="Caminho do diretório de questões."),
    ] = None,
) -> None:
    """Sincroniza as unidades e questões do disco com o banco de dados."""
    target_dir = caminho_dir if caminho_dir is not None else get_settings().questions_dir

    if not target_dir.exists() or not target_dir.is_dir():
        typer.echo(f"Erro fatal: o diretório '{target_dir}' não existe.", err=True)
        raise typer.Exit(code=2)

    scanned = scan_and_validate_questions_dir(target_dir)

    if scanned.has_errors:
        report = SyncReport(issues=list(scanned.issues))
        typer.echo(format_sync_report(str(target_dir), report))
        raise typer.Exit(code=1)

    try:
        with transaction() as conn:
            report = sync_questions(conn, scanned)
    except Exception as exc:
        typer.echo(f"Erro fatal de banco de dados: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    finally:
        close_pool()

    typer.echo(format_sync_report(str(target_dir), report))


if __name__ == "__main__":
    app()
