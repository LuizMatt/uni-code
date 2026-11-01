import os
import re
import shutil
import subprocess
import sys
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Annotated

import typer

from unicode.config import get_settings
from unicode.daemon.client import (
    DaemonClient,
    DaemonClientError,
    DaemonConnectionError,
    DaemonRemoteError,
)
from unicode.models.assignment import QuestionStatus
from unicode.models.attempt import StudentFeedback

app = typer.Typer(
    name="unicode",
    help="UniCode - Ferramenta de linha de comando do aluno.",
    add_completion=False,
)

_CODE_BLOCK_RE = re.compile(r"```(?:python|py)\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)

_STATE_LABELS: dict[str, str] = {
    "pending": "pendente",
    "passed": "aprovada",
    "exhausted": "esgotada",
    "replaced": "substituída",
}

_FEEDBACK_LABELS: dict[str, str] = {
    "passed": "APROVADA",
    "failed": "REPROVADA",
    "error": "ERRO",
}


class LocalContextError(Exception):
    """Raised when the local question folder or solution.py cannot be located."""


def _require_session_token() -> str:
    token = os.environ.get("UNICODE_SESSION", "").strip()
    if not token:
        typer.echo(
            "Erro: variável UNICODE_SESSION não definida (sessão não iniciada).",
            err=True,
        )
        raise typer.Exit(code=2)
    return token


def resolve_local_question_files(
    question_slug: str | None,
    unit_code: str | None,
    file_path: Path | None,
    *,
    cwd: Path,
    workspace_dir: Path,
) -> tuple[str, str | None, Path, Path | None]:
    """Resolve (question_slug, unit_code, solution_path, readme_path) in student workspace."""
    if file_path is not None:
        if not file_path.exists() or not file_path.is_file():
            raise LocalContextError(f"arquivo '{file_path}' não encontrado")
        resolved_file = file_path.resolve()
        inferred_slug = question_slug or resolved_file.parent.name
        inferred_unit = unit_code
        if inferred_unit is None and resolved_file.parent.parent != resolved_file.parent:
            parent_name = resolved_file.parent.parent.name
            if parent_name and not parent_name.startswith("."):
                inferred_unit = parent_name
        readme_candidate = resolved_file.parent / "README.md"
        return (
            inferred_slug,
            inferred_unit,
            resolved_file,
            readme_candidate if readme_candidate.exists() else None,
        )

    if question_slug is None:
        sol_here = cwd / "solution.py"
        if sol_here.exists() and sol_here.is_file():
            slug = cwd.name
            inferred_unit = unit_code
            if inferred_unit is None and cwd.parent != cwd:
                inferred_unit = cwd.parent.name
            readme_here = cwd / "README.md"
            return (
                slug,
                inferred_unit,
                sol_here,
                readme_here if readme_here.exists() else None,
            )
        raise LocalContextError(
            "informe o slug da questão ou execute o comando dentro da pasta da questão"
        )

    slug = question_slug.strip()
    candidates: list[tuple[Path, str | None]] = []

    if cwd.name == slug:
        inferred = unit_code or (cwd.parent.name if cwd.parent != cwd else None)
        candidates.append((cwd / "solution.py", inferred))

    candidates.append((cwd / slug / "solution.py", unit_code or cwd.name))

    if unit_code is not None:
        candidates.append((cwd / unit_code / slug / "solution.py", unit_code))
        candidates.append((workspace_dir / unit_code / slug / "solution.py", unit_code))

    for base in (cwd, workspace_dir):
        if base.exists() and base.is_dir():
            for child in sorted(base.iterdir()):
                if (
                    child.is_dir()
                    and not child.name.startswith(".")
                    and child.name != "_archive"
                ):
                    cand = child / slug / "solution.py"
                    candidates.append((cand, unit_code or child.name))

    for sol_cand, u_cand in candidates:
        if sol_cand.exists() and sol_cand.is_file():
            readme_cand = sol_cand.parent / "README.md"
            return (
                slug,
                u_cand,
                sol_cand,
                readme_cand if readme_cand.exists() else None,
            )

    raise LocalContextError(
        f"arquivo 'solution.py' não encontrado para a questão '{slug}'"
    )


def extract_readme_assert_blocks(readme_text: str) -> list[str]:
    """Extract ```python code blocks containing assert statements from README.md."""
    blocks: list[str] = []
    for match in _CODE_BLOCK_RE.finditer(readme_text):
        block = match.group(1).strip()
        if any(line.strip().startswith("assert ") for line in block.splitlines()):
            blocks.append(block)
    return blocks


def run_local_public_examples(
    solution_path: Path,
    readme_path: Path | None,
    *,
    timeout_seconds: int = 5,
) -> tuple[bool, int, str]:
    """Run public assert examples from README.md and any local test_*.py against solution.py."""
    if not solution_path.exists() or not solution_path.is_file():
        raise LocalContextError(f"arquivo '{solution_path}' não encontrado")

    blocks: list[str] = []
    if readme_path is not None and readme_path.exists():
        blocks = extract_readme_assert_blocks(readme_path.read_text(encoding="utf-8"))

    assert_lines: list[str] = []
    for block in blocks:
        for line in block.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                assert_lines.append(stripped)

    local_test_files = sorted(
        p
        for p in solution_path.parent.glob("test_*.py")
        if p.is_file() and p.name != "test_eval.py"
    )

    if not assert_lines and not local_test_files:
        return (
            False,
            0,
            "Nenhum exemplo público com 'assert' encontrado no README.md da questão.",
        )

    total_count = len(assert_lines) + len(local_test_files)
    tmp_dir = Path(tempfile.mkdtemp(prefix="unicode-local-test-"))
    try:
        shutil.copyfile(solution_path, tmp_dir / "solution.py")
        for test_file in local_test_files:
            shutil.copyfile(test_file, tmp_dir / test_file.name)

        env = {
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "TEMP": str(tmp_dir),
            "TMP": str(tmp_dir),
            "PYTHONPATH": str(tmp_dir),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        outputs: list[str] = []
        all_ok = True

        if assert_lines:
            harness_lines = [
                "import sys",
                f"sys.path.insert(0, {str(tmp_dir)!r})",
                "import traceback",
                "try:",
                "    import solution",
                "    from solution import *",
                "except Exception as exc:",
                "    print(f'FALHOU ao importar solution.py: {type(exc).__name__}: {exc}')",
                "    sys.exit(1)",
                f"examples = {assert_lines!r}",
                "passed = 0",
                "for idx, stmt in enumerate(examples, 1):",
                "    try:",
                "        exec(stmt, globals())",
                "        passed += 1",
                "        print(f'  [OK] Exemplo {idx}: {stmt}')",
                "    except AssertionError:",
                "        print(f'  [FALHA] Exemplo {idx} falhou: {stmt}')",
                (
                    "        print("
                    "f'\\nResultado local: FALHOU ({passed}/{len(examples)} exemplos passaram)')"
                ),
                "        sys.exit(1)",
                "    except Exception as exc:",
                "        err_name = type(exc).__name__",
                "        print(f'  [ERRO] Exemplo {idx} ({stmt}) levantou {err_name}: {exc}')",
                (
                    "        print("
                    "f'\\nResultado local: FALHOU ({passed}/{len(examples)} exemplos passaram)')"
                ),
                "        sys.exit(1)",
                (
                    "print("
                    "f'\\nResultado local: PASSOU ({passed}/{len(examples)} "
                    "exemplos públicos passaram)')"
                ),
                "sys.exit(0)",
            ]
            harness_path = tmp_dir / "_run_examples.py"
            harness_path.write_text("\n".join(harness_lines) + "\n", encoding="utf-8")

            try:
                proc = subprocess.run(
                    [sys.executable, "-I", str(harness_path)],
                    cwd=str(tmp_dir),
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                return (
                    False,
                    total_count,
                    f"Resultado local: FALHOU (tempo limite de {timeout_seconds}s excedido)",
                )

            combined = (proc.stdout + ("\n" + proc.stderr if proc.stderr else "")).strip()
            if combined:
                outputs.append(combined)
            if proc.returncode != 0:
                all_ok = False

        if local_test_files and all_ok:
            try:
                proc_py = subprocess.run(
                    [
                        sys.executable,
                        "-I",
                        "-m",
                        "pytest",
                        "-q",
                        "-p",
                        "no:cacheprovider",
                        *[p.name for p in local_test_files],
                    ],
                    cwd=str(tmp_dir),
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                return (
                    False,
                    total_count,
                    f"Resultado local: FALHOU (tempo limite de {timeout_seconds}s excedido)",
                )

            py_combined = (
                proc_py.stdout + ("\n" + proc_py.stderr if proc_py.stderr else "")
            ).strip()
            if py_combined:
                outputs.append(py_combined)
            if proc_py.returncode == 0:
                outputs.append("Resultado local (pytest): PASSOU")
            else:
                all_ok = False
                outputs.append("Resultado local (pytest): FALHOU")

        return (all_ok, total_count, "\n".join(outputs).strip())
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def format_start_output(
    unit_code: str,
    created: bool,
    questions: list[QuestionStatus],
) -> str:
    header = (
        f"Unidade {unit_code} iniciada (novo sorteio realizado):"
        if created
        else f"Unidade {unit_code} (sorteio ativo recuperado):"
    )
    lines = [header]
    for q in questions:
        state_lbl = _STATE_LABELS.get(q.state, q.state)
        lines.append(
            f"  - {q.question_slug}: {q.question_title} "
            f"[{state_lbl}, tentativas restantes: {q.attempts_remaining}/3] "
            f"-> {q.unit_code}/{q.question_slug}/solution.py"
        )
    return "\n".join(lines)


def format_status_output(questions: list[QuestionStatus]) -> str:
    if not questions:
        return "Nenhuma questão sorteada até o momento. Use 'unicode start <unidade>' para iniciar."

    by_unit: dict[str, list[QuestionStatus]] = {}
    for q in questions:
        by_unit.setdefault(q.unit_code, []).append(q)

    blocks: list[str] = []
    headers = ("QUESTÃO", "TÍTULO", "ESTADO", "TENTATIVAS", "PONTOS")

    for u_code, items in by_unit.items():
        total_points = sum((item.points for item in items), Decimal("0.0"))
        rows: list[tuple[str, str, str, str, str]] = []
        for item in items:
            state_lbl = _STATE_LABELS.get(item.state, item.state)
            att_str = f"{item.attempts_used}/3 ({item.attempts_remaining})"
            rows.append(
                (
                    item.question_slug,
                    item.question_title,
                    state_lbl,
                    att_str,
                    f"{item.points:.1f}",
                )
            )
        widths = [len(h) for h in headers]
        for r in rows:
            for idx, val in enumerate(r):
                widths[idx] = max(widths[idx], len(val))
        fmt = "  ".join(f"{{:<{w}}}" for w in widths)
        unit_lines = [
            f"Unidade: {u_code} (Nota: {total_points:.1f} / 1.0)",
            fmt.format(*headers),
        ]
        for r in rows:
            unit_lines.append(fmt.format(*r))
        blocks.append("\n".join(unit_lines))

    return "\n\n".join(blocks)


def format_submit_output(
    unit_code: str,
    question_slug: str,
    feedback: StudentFeedback,
) -> str:
    res_label = _FEEDBACK_LABELS.get(feedback.status, feedback.status.upper())
    state_label = _STATE_LABELS.get(feedback.assignment_state, feedback.assignment_state)
    lines = [
        f"Submissão: {unit_code} / {question_slug} (tentativa {feedback.attempt_number}/3)",
        f"  resultado:            {res_label}",
        f"  testes aprovados:     {feedback.tests_passed}/{feedback.tests_total}",
        f"  tentativas restantes: {feedback.attempts_remaining}",
        f"  estado da questão:    {state_label}",
        f"  pontos na questão:    {feedback.points:.1f}",
    ]
    if feedback.first_failed_test:
        lines.append(f"  primeiro teste falho: {feedback.first_failed_test}")
    if feedback.error_category:
        lines.append(f"  categoria do erro:    {feedback.error_category}")
    return "\n".join(lines)


def _handle_daemon_error(exc: DaemonClientError) -> None:
    if isinstance(exc, DaemonRemoteError):
        if exc.code == "auth_error":
            typer.echo(f"Erro de autenticação: {exc.message}", err=True)
            raise typer.Exit(code=2)
        typer.echo(f"Erro: {exc.message}", err=True)
        raise typer.Exit(code=1)
    if isinstance(exc, DaemonConnectionError):
        typer.echo(f"Erro de conexão com o servidor: {exc}", err=True)
        raise typer.Exit(code=2)
    typer.echo(f"Erro de comunicação: {exc}", err=True)
    raise typer.Exit(code=2)


@app.command("start")
def start_cmd(
    unidade: Annotated[
        str,
        typer.Argument(help="Código da unidade a iniciar (ex.: unit-01)."),
    ],
) -> None:
    """Realiza ou recupera o sorteio de questões da unidade e prepara a pasta."""
    token = _require_session_token()
    client = DaemonClient()
    try:
        created, questions = client.start_unit(token, unidade)
    except DaemonClientError as exc:
        _handle_daemon_error(exc)
        return

    typer.echo(format_start_output(unidade, created, questions))


@app.command("status")
def status_cmd(
    unidade: Annotated[
        str | None,
        typer.Option("--unidade", "-u", help="Filtrar por código da unidade."),
    ] = None,
) -> None:
    """Mostra questões sorteadas, tentativas usadas/restantes e pontuação."""
    token = _require_session_token()
    client = DaemonClient()
    try:
        questions = client.get_status(token, unit_code=unidade)
    except DaemonClientError as exc:
        _handle_daemon_error(exc)
        return

    typer.echo(format_status_output(questions))


@app.command("submit")
def submit_cmd(
    questao: Annotated[
        str | None,
        typer.Argument(help="Slug da questão (opcional se estiver dentro da pasta dela)."),
    ] = None,
    unidade: Annotated[
        str | None,
        typer.Option("--unidade", "-u", help="Código da unidade (opcional)."),
    ] = None,
    arquivo: Annotated[
        Path | None,
        typer.Option("--arquivo", "-f", help="Caminho explícito do solution.py."),
    ] = None,
) -> None:
    """Envia solution.py ao daemon e avalia nos testes ocultos (consome 1 tentativa)."""
    token = _require_session_token()
    settings = get_settings()
    try:
        slug, inferred_unit, sol_path, _ = resolve_local_question_files(
            questao,
            unidade,
            arquivo,
            cwd=Path.cwd(),
            workspace_dir=settings.student_workspace_dir,
        )
    except LocalContextError as exc:
        typer.echo(f"Erro: {exc}", err=True)
        raise typer.Exit(code=2) from None

    try:
        code = sol_path.read_text(encoding="utf-8")
    except Exception as exc:
        typer.echo(f"Erro ao ler '{sol_path}': {exc}", err=True)
        raise typer.Exit(code=2) from None

    if not code.strip():
        typer.echo("Erro: o arquivo solution.py está vazio.", err=True)
        raise typer.Exit(code=1)

    client = DaemonClient()
    try:
        resolved_unit, resolved_slug, feedback = client.submit(
            token,
            slug,
            code,
            unit_code=unidade or inferred_unit,
        )
    except DaemonClientError as exc:
        _handle_daemon_error(exc)
        return

    typer.echo(format_submit_output(resolved_unit, resolved_slug, feedback))
    if feedback.status != "passed":
        raise typer.Exit(code=1)


@app.command("test")
def test_cmd(
    questao: Annotated[
        str | None,
        typer.Argument(help="Slug da questão (opcional se estiver dentro da pasta dela)."),
    ] = None,
    unidade: Annotated[
        str | None,
        typer.Option("--unidade", "-u", help="Código da unidade (opcional)."),
    ] = None,
    arquivo: Annotated[
        Path | None,
        typer.Option("--arquivo", "-f", help="Caminho explícito do solution.py."),
    ] = None,
) -> None:
    """Roda apenas os exemplos públicos localmente (não consome tentativa)."""
    settings = get_settings()
    try:
        slug, _, sol_path, readme_path = resolve_local_question_files(
            questao,
            unidade,
            arquivo,
            cwd=Path.cwd(),
            workspace_dir=settings.student_workspace_dir,
        )
    except LocalContextError as exc:
        typer.echo(f"Erro: {exc}", err=True)
        raise typer.Exit(code=2) from None

    typer.echo(
        f"Execução local de exemplos públicos para '{slug}' (não consome tentativa):"
    )
    ok, _, output = run_local_public_examples(sol_path, readme_path)
    typer.echo(output)
    if not ok:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
