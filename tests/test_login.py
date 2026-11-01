from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from typer.testing import CliRunner

from tests.support import ROOT, TEST_DAEMON_URL, TEST_OWNER_URL
from unicode.config import Settings
from unicode.db import DictConnection
from unicode.login import (
    GENERIC_LOGIN_ERROR_MESSAGE,
    app,
    build_student_shell_docker_cmd,
    extract_client_ip,
    run_login_session,
)
from unicode.services.assignments import draw_assignments
from unicode.services.questions import scan_and_validate_questions_dir, sync_questions
from unicode.services.sessions import (
    SessionAuthError,
    authenticate_session,
)

cli_runner = CliRunner()


def test_extract_client_ip_from_ssh_env() -> None:
    assert extract_client_ip({"SSH_CONNECTION": "198.51.100.7 54321 10.0.0.1 22"}) == "198.51.100.7"
    assert extract_client_ip({"SSH_CLIENT": "203.0.113.5 50000 22"}) == "203.0.113.5"
    assert extract_client_ip({"SSH_CONNECTION": "   ", "SSH_CLIENT": ""}) == "local"
    assert extract_client_ip({}) == "local"


def test_build_student_shell_docker_cmd_unix_and_tcp_sockets(tmp_path: Path) -> None:
    ws_dir = tmp_path / "workspaces" / "2026001"
    ws_dir.mkdir(parents=True)
    sock_file = tmp_path / "run" / "daemon.sock"

    settings_unix = Settings(
        daemon_socket_path=sock_file,
        student_shell_image="unicode-aluno-shell",
        student_shell_memory_mb=512,
        student_shell_cpus=1.0,
        student_shell_pids_limit=128,
        student_shell_user="1000:1000",
    )
    cmd = build_student_shell_docker_cmd(
        container_name="unicode-shell-2026001-abcd1234",
        student_workspace_dir=ws_dir,
        session_token="secret-token-xyz",
        settings=settings_unix,
        interactive_tty=True,
    )

    assert cmd[:4] == ["docker", "run", "-it", "--rm"]
    assert "--network" in cmd and cmd[cmd.index("--network") + 1] == "none"
    assert "--read-only" in cmd
    assert "--cap-drop" in cmd and cmd[cmd.index("--cap-drop") + 1] == "ALL"
    assert "--security-opt" in cmd and cmd[cmd.index("--security-opt") + 1] == "no-new-privileges"
    assert "--pids-limit" in cmd and cmd[cmd.index("--pids-limit") + 1] == "128"
    assert "--memory" in cmd and cmd[cmd.index("--memory") + 1] == "512m"
    assert "--memory-swap" in cmd and cmd[cmd.index("--memory-swap") + 1] == "512m"
    assert "--cpus" in cmd and cmd[cmd.index("--cpus") + 1] == "1.0"
    assert "--user" in cmd and cmd[cmd.index("--user") + 1] == "1000:1000"
    assert "--workdir" in cmd and cmd[cmd.index("--workdir") + 1] == "/home/aluno"
    assert f"{ws_dir.resolve()}:/home/aluno:rw" in cmd
    assert f"{sock_file.resolve()}:/run/unicode/daemon.sock:rw" in cmd
    assert "UNICODE_SESSION=secret-token-xyz" in cmd
    assert "UNICODE_DAEMON_SOCKET_PATH=/run/unicode/daemon.sock" in cmd
    assert "UNICODE_STUDENT_WORKSPACE_DIR=/home/aluno" in cmd
    assert cmd[-1] == "unicode-aluno-shell"

    # Non-TTY and TCP daemon endpoint
    settings_tcp = Settings(daemon_socket_path=Path("tcp://127.0.0.1:9999"))
    cmd_tcp = build_student_shell_docker_cmd(
        container_name="unicode-shell-2026001-tcp",
        student_workspace_dir=ws_dir,
        session_token="tok-2",
        settings=settings_tcp,
        interactive_tty=False,
    )
    assert cmd_tcp[2] == "-i"
    assert any(arg.startswith("UNICODE_DAEMON_SOCKET_PATH=tcp://") for arg in cmd_tcp)


@pytest.fixture
def clean_login_pool(
    migrated_db: None,
) -> Iterator[ConnectionPool[DictConnection]]:
    with psycopg.connect(TEST_OWNER_URL) as owner:
        owner.execute(
            "TRUNCATE attempts, assignments, sessions, questions, units, students, audit_log "
            "RESTART IDENTITY CASCADE"
        )
    pool: ConnectionPool[DictConnection] = ConnectionPool(
        conninfo=TEST_DAEMON_URL,
        min_size=1,
        max_size=4,
        kwargs={"row_factory": dict_row},
        open=True,
    )
    try:
        yield pool
    finally:
        pool.close()
        with psycopg.connect(TEST_OWNER_URL) as owner:
            owner.execute(
                "TRUNCATE attempts, assignments, sessions, questions, units, students, audit_log "
                "RESTART IDENTITY CASCADE"
            )


class InspectingShellRunner:
    def __init__(
        self,
        pool: ConnectionPool[DictConnection],
        *,
        exit_code: int = 0,
        raise_exc: bool = False,
    ) -> None:
        self.pool = pool
        self.exit_code = exit_code
        self.raise_exc = raise_exc
        self.called = False
        self.captured_token = ""
        self.captured_workspace: Path | None = None
        self.session_was_active_inside_shell = False

    def run(
        self,
        *,
        registration: str,
        student_workspace_dir: Path,
        session_token: str,
        settings: Settings,
    ) -> int:
        self.called = True
        self.captured_token = session_token
        self.captured_workspace = student_workspace_dir
        with self.pool.connection() as conn:
            s = authenticate_session(conn, session_token)
            self.session_was_active_inside_shell = s.student_registration == registration
        if self.raise_exc:
            raise RuntimeError("simulated container crash")
        return self.exit_code


@pytest.mark.db
def test_run_login_session_provisions_workspace_and_revokes_on_exit(
    clean_login_pool: ConnectionPool[DictConnection],
    tmp_path: Path,
) -> None:
    scanned = scan_and_validate_questions_dir(ROOT / "questions")
    with clean_login_pool.connection() as conn, conn.transaction():
        sync_questions(conn, scanned)
        conn.execute(
            "INSERT INTO students (registration, email, name) "
            "VALUES ('2026001', 'aluno@uni.edu', 'Aluno')"
        )
        draw = draw_assignments(conn, "2026001", "unit-01")

    settings = Settings(
        questions_dir=ROOT / "questions",
        workspaces_dir=tmp_path / "workspaces",
    )
    runner = InspectingShellRunner(clean_login_pool, exit_code=0)

    rc = run_login_session(
        "ALUNO@uni.edu",
        "2026001",
        client_ip="198.51.100.25",
        settings=settings,
        pool=clean_login_pool,
        runner=runner,
    )
    assert rc == 0
    assert runner.called is True
    assert runner.session_was_active_inside_shell is True
    assert runner.captured_workspace == tmp_path / "workspaces" / "2026001"

    # Active assignment files were provisioned on login
    for a in draw.assignments:
        q_dir = tmp_path / "workspaces" / "2026001" / a.unit_code / a.question_slug
        assert (q_dir / "README.md").is_file()
        assert (q_dir / "solution.py").is_file()

    # After container exits, session token is revoked and logout is audited
    with clean_login_pool.connection() as conn:
        with pytest.raises(SessionAuthError):
            authenticate_session(conn, runner.captured_token)
        logout_row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM audit_log "
            "WHERE action = 'logout' AND actor = 'student:2026001'"
        ).fetchone()
        assert logout_row is not None
        assert int(str(logout_row["cnt"])) == 1


@pytest.mark.db
def test_run_login_session_revokes_session_even_if_runner_crashes(
    clean_login_pool: ConnectionPool[DictConnection],
    tmp_path: Path,
) -> None:
    with clean_login_pool.connection() as conn, conn.transaction():
        conn.execute(
            "INSERT INTO students (registration, email, name) "
            "VALUES ('2026001', 'aluno@uni.edu', 'Aluno')"
        )
    settings = Settings(
        questions_dir=ROOT / "questions",
        workspaces_dir=tmp_path / "workspaces",
    )
    runner = InspectingShellRunner(clean_login_pool, raise_exc=True)

    with pytest.raises(RuntimeError, match="simulated container crash"):
        run_login_session(
            "aluno@uni.edu",
            "2026001",
            client_ip="198.51.100.26",
            settings=settings,
            pool=clean_login_pool,
            runner=runner,
        )

    with clean_login_pool.connection() as conn, pytest.raises(SessionAuthError):
        authenticate_session(conn, runner.captured_token)


@pytest.mark.db
def test_unicode_login_cli_commits_failed_attempts_and_enforces_rate_limit(
    clean_login_pool: ConnectionPool[DictConnection],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with clean_login_pool.connection() as conn, conn.transaction():
        conn.execute(
            "INSERT INTO students (registration, email, name) "
            "VALUES ('2026001', 'aluno@uni.edu', 'Aluno')"
        )

    settings = Settings(
        questions_dir=ROOT / "questions",
        workspaces_dir=tmp_path / "workspaces",
        login_rate_limit_max_failures=3,
        login_rate_limit_window_seconds=60,
    )
    runner = InspectingShellRunner(clean_login_pool)

    monkeypatch.setenv("SSH_CONNECTION", "203.0.113.77 51111 10.0.0.1 22")
    monkeypatch.setattr("unicode.login.get_settings", lambda: settings)
    monkeypatch.setattr("unicode.login._get_default_pool", lambda: clean_login_pool)
    monkeypatch.setattr("unicode.login._get_default_runner", lambda: runner)

    # 3 failed attempts via CLI -> each returns exit code 1 with generic message and commits to DB
    for _ in range(3):
        res = cli_runner.invoke(app, input="errado@uni.edu\n2026001\n")
        assert res.exit_code == 1
        assert GENERIC_LOGIN_ERROR_MESSAGE in res.output
        assert runner.called is False

    # 4th attempt with VALID credentials from same IP is blocked by rate limit
    res_blocked = cli_runner.invoke(app, input="aluno@uni.edu\n2026001\n")
    assert res_blocked.exit_code == 1
    assert GENERIC_LOGIN_ERROR_MESSAGE in res_blocked.output
    assert runner.called is False

    # Valid login from a different IP succeeds
    monkeypatch.setenv("SSH_CONNECTION", "203.0.113.88 51111 10.0.0.1 22")
    res_ok = cli_runner.invoke(app, input="aluno@uni.edu\n2026001\n")
    assert res_ok.exit_code == 0
    assert runner.called is True


def test_student_shell_dockerfile_sshd_config_and_dockerignore() -> None:
    dockerignore = ROOT / ".dockerignore"
    assert dockerignore.is_file()
    ignore_lines = {
        line.strip()
        for line in dockerignore.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    assert "questions/" in ignore_lines or "questions" in ignore_lines
    assert ".env" in ignore_lines
    assert "workspaces/" in ignore_lines or "workspaces" in ignore_lines

    dockerfile = ROOT / "docker" / "aluno-shell" / "Dockerfile"
    assert dockerfile.is_file()
    df_text = dockerfile.read_text(encoding="utf-8")
    assert "FROM python:3.12-slim" in df_text
    assert "nano" in df_text
    assert "USER 1000:1000" in df_text
    assert "WORKDIR /home/aluno" in df_text

    sshd_cfg = ROOT / "docker" / "aluno-shell" / "sshd_config"
    assert sshd_cfg.is_file()
    sshd_text = sshd_cfg.read_text(encoding="utf-8")
    assert "Match User aluno" in sshd_text
    assert "ForceCommand /usr/local/bin/unicode-login" in sshd_text
    assert "AllowTcpForwarding no" in sshd_text
    assert "X11Forwarding no" in sshd_text
    assert "PermitTunnel no" in sshd_text
    assert "AllowAgentForwarding no" in sshd_text

