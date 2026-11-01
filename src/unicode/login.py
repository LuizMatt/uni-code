import json
import os
import signal
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol
from uuid import uuid4

import typer
from psycopg_pool import ConnectionPool

from unicode.config import Settings, get_settings
from unicode.daemon.protocol import parse_endpoint
from unicode.db import DictConnection, get_pool, transaction
from unicode.models.assignment import Assignment
from unicode.models.session import IssuedSession
from unicode.services.assignments import (
    ensure_student_workspace,
    list_all_active_assignments,
)
from unicode.services.sessions import (
    LoginAuthError,
    authenticate_student_login,
    revoke_session,
)

GENERIC_LOGIN_ERROR_MESSAGE = "Erro: credenciais inválidas."

app = typer.Typer(
    name="unicode-login",
    help="Entrypoint ForceCommand SSH para autenticação e abertura do shell isolado do aluno.",
    add_completion=False,
)


class ShellRunner(Protocol):
    """Protocol for launching the interactive student shell container."""

    def run(
        self,
        *,
        registration: str,
        student_workspace_dir: Path,
        session_token: str,
        settings: Settings,
    ) -> int: ...


def extract_client_ip(env: Mapping[str, str] | None = None) -> str:
    """Extract client IP address from OpenSSH environment variables."""
    source = env if env is not None else os.environ
    for var_name in ("SSH_CONNECTION", "SSH_CLIENT"):
        raw = source.get(var_name, "").strip()
        if raw:
            parts = raw.split()
            if parts and parts[0]:
                return parts[0]
    return "local"


def build_student_shell_docker_cmd(
    *,
    container_name: str,
    student_workspace_dir: Path,
    session_token: str,
    settings: Settings,
    interactive_tty: bool = True,
) -> list[str]:
    """Build the hardened `docker run` command for the student's interactive container."""
    resolved_ws = student_workspace_dir.resolve()
    cmd = [
        "docker",
        "run",
        "-it" if interactive_tty else "-i",
        "--rm",
        "--name",
        container_name,
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        str(settings.student_shell_pids_limit),
        "--memory",
        f"{settings.student_shell_memory_mb}m",
        "--memory-swap",
        f"{settings.student_shell_memory_mb}m",
        "--cpus",
        str(settings.student_shell_cpus),
        "--user",
        settings.student_shell_user,
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m,mode=1777",
        "--workdir",
        "/home/aluno",
        "-v",
        f"{resolved_ws}:/home/aluno:rw",
    ]

    kind, addr = parse_endpoint(settings.daemon_socket_path)
    if kind == "unix":
        assert isinstance(addr, str)
        resolved_sock = Path(addr).resolve()
        cmd.extend(
            [
                "-v",
                f"{resolved_sock}:/run/unicode/daemon.sock:rw",
                "-e",
                "UNICODE_DAEMON_SOCKET_PATH=/run/unicode/daemon.sock",
            ]
        )
    else:
        assert isinstance(addr, tuple)
        host, port = addr
        cmd.extend(
            [
                "-e",
                f"UNICODE_DAEMON_SOCKET_PATH=tcp://{host}:{port}",
            ]
        )

    cmd.extend(
        [
            "-e",
            f"UNICODE_SESSION={session_token}",
            "-e",
            "UNICODE_STUDENT_WORKSPACE_DIR=/home/aluno",
            "-e",
            "HOME=/home/aluno",
            settings.student_shell_image,
        ]
    )
    return cmd


class DockerShellRunner:
    """Default Docker-based student shell runner."""

    def run(
        self,
        *,
        registration: str,
        student_workspace_dir: Path,
        session_token: str,
        settings: Settings,
    ) -> int:
        container_name = f"unicode-shell-{registration}-{uuid4().hex[:8]}"
        interactive_tty = sys.stdin.isatty() and sys.stdout.isatty()
        cmd = build_student_shell_docker_cmd(
            container_name=container_name,
            student_workspace_dir=student_workspace_dir,
            session_token=session_token,
            settings=settings,
            interactive_tty=interactive_tty,
        )
        proc = subprocess.run(cmd, check=False)
        return int(proc.returncode)


def _get_default_pool() -> ConnectionPool[DictConnection]:
    return get_pool()


def _get_default_runner() -> ShellRunner:
    return DockerShellRunner()


def run_login_session(
    email: str,
    registration: str,
    *,
    client_ip: str = "local",
    settings: Settings | None = None,
    pool: ConnectionPool[DictConnection] | None = None,
    runner: ShellRunner | None = None,
) -> int:
    """Authenticate student, provision workspace, run container, and revoke session on exit."""
    cfg = settings if settings is not None else get_settings()
    active_pool = pool if pool is not None else _get_default_pool()
    shell_runner = runner if runner is not None else _get_default_runner()

    auth_error: LoginAuthError | None = None
    issued: IssuedSession | None = None
    active_assignments: list[Assignment] = []

    with transaction(active_pool) as conn:
        try:
            issued = authenticate_student_login(
                conn,
                email,
                registration,
                client_ip=client_ip,
                ttl_seconds=cfg.session_ttl_seconds,
                max_failures=cfg.login_rate_limit_max_failures,
                window_seconds=cfg.login_rate_limit_window_seconds,
            )
            active_assignments = list_all_active_assignments(
                conn,
                issued.session.student_registration,
            )
        except LoginAuthError as exc:
            auth_error = exc

    if auth_error is not None or issued is None:
        raise auth_error or LoginAuthError("credenciais inválidas")

    student_reg = issued.session.student_registration
    try:
        student_ws = ensure_student_workspace(
            cfg.workspaces_dir,
            cfg.questions_dir,
            student_reg,
            active_assignments,
        )
        return shell_runner.run(
            registration=student_reg,
            student_workspace_dir=student_ws,
            session_token=issued.token,
            settings=cfg,
        )
    finally:
        with transaction(active_pool) as conn:
            revoke_session(conn, issued.token)
            conn.execute(
                "INSERT INTO audit_log (actor, action, details) VALUES (%s, %s, %s)",
                (
                    f"student:{student_reg}",
                    "logout",
                    json.dumps({"student_registration": student_reg, "ip": client_ip}),
                ),
            )


def _register_exit_signal_handlers() -> None:
    def _sig_handler(signum: int, frame: object) -> None:
        sys.exit(128 + signum)

    for sig_name in ("SIGTERM", "SIGHUP"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            try:
                signal.signal(sig, _sig_handler)
            except (ValueError, OSError):
                pass


@app.command()
def login_cmd() -> None:
    """Autentica o aluno via SSH (ForceCommand) e inicia o container unicode-aluno-shell."""
    _register_exit_signal_handlers()
    typer.echo("=== UniCode — Ambiente de Questões ===")
    try:
        email = str(typer.prompt("Email", prompt_suffix=": "))
        registration = str(typer.prompt("Matrícula", prompt_suffix=": "))
    except (typer.Abort, EOFError, KeyboardInterrupt):
        typer.echo(GENERIC_LOGIN_ERROR_MESSAGE, err=True)
        raise typer.Exit(code=1) from None

    client_ip = extract_client_ip()
    try:
        exit_code = run_login_session(
            email,
            registration,
            client_ip=client_ip,
        )
    except LoginAuthError:
        typer.echo(GENERIC_LOGIN_ERROR_MESSAGE, err=True)
        raise typer.Exit(code=1) from None
    except Exception:
        typer.echo("Erro interno ao iniciar a sessão.", err=True)
        raise typer.Exit(code=1) from None

    if exit_code != 0:
        raise typer.Exit(code=exit_code)


if __name__ == "__main__":
    app()
