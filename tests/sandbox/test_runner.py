import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from unicode.config import Settings
from unicode.sandbox.runner import (
    DockerSandboxRunner,
    _build_docker_run_cmd,
    _parse_container_execution,
    run_in_sandbox,
)


def test_build_docker_run_cmd_includes_all_hardening_flags(tmp_path: Path) -> None:
    settings = Settings(
        sandbox_image="unicode-sandbox:test",
        sandbox_timeout_seconds=4,
        sandbox_memory_mb=128,
        sandbox_cpus=0.5,
        sandbox_pids_limit=32,
    )
    cmd = _build_docker_run_cmd(
        container_name="unicode-sbx-123",
        workspace_dir=tmp_path,
        settings=settings,
    )
    assert cmd[:3] == ["docker", "run", "--name"]
    assert "unicode-sbx-123" in cmd
    assert "--network" in cmd and cmd[cmd.index("--network") + 1] == "none"
    assert "--read-only" in cmd
    assert "--cap-drop" in cmd and cmd[cmd.index("--cap-drop") + 1] == "ALL"
    assert "--security-opt" in cmd and cmd[cmd.index("--security-opt") + 1] == "no-new-privileges"
    assert "--pids-limit" in cmd and cmd[cmd.index("--pids-limit") + 1] == "32"
    assert "--memory" in cmd and cmd[cmd.index("--memory") + 1] == "128m"
    assert "--memory-swap" in cmd and cmd[cmd.index("--memory-swap") + 1] == "128m"
    assert "--cpus" in cmd and cmd[cmd.index("--cpus") + 1] == "0.5"
    assert "--user" in cmd and cmd[cmd.index("--user") + 1] == "65534:65534"
    assert "--tmpfs" in cmd
    assert f"{tmp_path.resolve()}:/workspace:ro" in cmd
    assert cmd[-2:] == ["unicode-sandbox:test", "4"]


def test_parse_container_execution_all_passed() -> None:
    envelope = {
        "timed_out": False,
        "exit_code": 0,
        "stdout": "...\n3 passed in 0.02s\n",
        "stderr": "",
        "report": {
            "summary": {"total": 3, "passed": 3},
            "collectors": [{"nodeid": "test_eval.py", "outcome": "passed"}],
            "tests": [
                {"nodeid": "test_eval.py::test_a", "outcome": "passed"},
                {"nodeid": "test_eval.py::test_b", "outcome": "passed"},
                {"nodeid": "test_eval.py::test_c", "outcome": "passed"},
            ],
        },
    }
    res = _parse_container_execution(
        returncode=0,
        stdout=json.dumps(envelope),
        stderr="",
    )
    assert res.outcome == "passed"
    assert res.tests_total == 3
    assert res.tests_passed == 3
    assert res.first_failed_test is None
    assert res.error_category is None


def test_parse_container_execution_partial_failure_extracts_first_failed_test() -> None:
    envelope = {
        "timed_out": False,
        "exit_code": 1,
        "stdout": "1 failed, 2 passed",
        "stderr": "",
        "report": {
            "summary": {"total": 3, "passed": 2, "failed": 1},
            "collectors": [{"nodeid": "test_eval.py", "outcome": "passed"}],
            "tests": [
                {"nodeid": "test_eval.py::test_positivos", "outcome": "passed"},
                {
                    "nodeid": "test_eval.py::test_negativos",
                    "outcome": "failed",
                    "call": {"longrepr": "assert 0 == -10"},
                },
                {"nodeid": "test_eval.py::test_zero", "outcome": "passed"},
            ],
        },
    }
    res = _parse_container_execution(
        returncode=1,
        stdout=json.dumps(envelope),
        stderr="",
    )
    assert res.outcome == "failed"
    assert res.tests_total == 3
    assert res.tests_passed == 2
    assert res.first_failed_test == "test_negativos"
    assert "assert 0 == -10" in res.diagnostic_output


def test_parse_container_execution_syntax_error_during_collection() -> None:
    envelope = {
        "timed_out": False,
        "exit_code": 2,
        "stdout": "",
        "stderr": "",
        "report": {
            "summary": {"total": 0},
            "collectors": [
                {
                    "nodeid": "test_eval.py",
                    "outcome": "failed",
                    "longrepr": "SyntaxError: invalid syntax (solution.py, line 1)",
                }
            ],
            "tests": [],
        },
    }
    res = _parse_container_execution(
        returncode=2,
        stdout=json.dumps(envelope),
        stderr="",
    )
    assert res.outcome == "error"
    assert res.tests_total == 0
    assert res.tests_passed == 0
    assert res.error_category == "SyntaxError"
    assert "SyntaxError" in res.diagnostic_output


def test_parse_container_execution_oom_killed() -> None:
    res = _parse_container_execution(
        returncode=137,
        stdout="",
        stderr="Killed",
    )
    assert res.outcome == "oom"
    assert res.tests_total == 0
    assert res.tests_passed == 0
    assert res.error_category == "MemoryError"


def test_parse_container_execution_internal_timeout() -> None:
    envelope = {
        "timed_out": True,
        "exit_code": -9,
        "stdout": "",
        "stderr": "TimeoutExpired",
        "report": None,
    }
    res = _parse_container_execution(
        returncode=0,
        stdout=json.dumps(envelope),
        stderr="",
    )
    assert res.outcome == "timeout"
    assert res.tests_total == 0
    assert res.tests_passed == 0
    assert res.error_category == "TimeoutError"


def test_runner_always_removes_container_on_host_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    test_eval = tmp_path / "test_eval.py"
    test_eval.write_text("def test_ok(): assert True\n", encoding="utf-8")

    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        if cmd[:2] == ["docker", "run"]:
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=5)
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    res = run_in_sandbox("x = 1\n", test_eval, settings=Settings(sandbox_timeout_seconds=2))
    assert res.outcome == "timeout"
    assert res.error_category == "TimeoutError"
    assert len(calls) == 2
    assert calls[0][:2] == ["docker", "run"]
    assert calls[1][:3] == ["docker", "rm", "-f"]


def test_parse_container_execution_non_zero_exit_with_all_tests_passed() -> None:
    envelope = {
        "timed_out": False,
        "exit_code": 1,
        "stdout": "3 passed",
        "stderr": "warning or abnormal exit",
        "report": {
            "summary": {"total": 3, "passed": 3},
            "collectors": [{"nodeid": "test_eval.py", "outcome": "passed"}],
            "tests": [
                {"nodeid": "test_eval.py::test_a", "outcome": "passed"},
                {"nodeid": "test_eval.py::test_b", "outcome": "passed"},
                {"nodeid": "test_eval.py::test_c", "outcome": "passed"},
            ],
        },
    }
    res = _parse_container_execution(
        returncode=1,
        stdout=json.dumps(envelope),
        stderr="warning or abnormal exit",
    )
    assert res.outcome == "failed"
    assert res.tests_total == 3
    assert res.tests_passed == 3


def test_runner_cleanup_error_does_not_mask_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    test_eval = tmp_path / "test_eval.py"
    test_eval.write_text("def test_ok(): assert True\n", encoding="utf-8")

    envelope = {
        "timed_out": False,
        "exit_code": 0,
        "stdout": "ok",
        "stderr": "",
        "report": {
            "summary": {"total": 1, "passed": 1},
            "collectors": [{"nodeid": "test_eval.py", "outcome": "passed"}],
            "tests": [{"nodeid": "test_eval.py::test_ok", "outcome": "passed"}],
        },
    }

    kw_records: list[dict[str, Any]] = []

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        kw_records.append(kwargs)
        if cmd[:2] == ["docker", "run"]:
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout=json.dumps(envelope), stderr=""
            )
        # docker rm raises an exception
        raise OSError("Host docker daemon communication failure")

    monkeypatch.setattr(subprocess, "run", fake_run)

    res = run_in_sandbox("x = 1\n", test_eval, settings=Settings(sandbox_timeout_seconds=2))
    assert res.outcome == "passed"
    assert res.tests_passed == 1
    # Check that encoding and errors were provided to subprocess.run
    assert kw_records[0].get("encoding") == "utf-8"
    assert kw_records[0].get("errors") == "replace"
    assert kw_records[1].get("encoding") == "utf-8"
    assert kw_records[1].get("errors") == "replace"


def test_runner_missing_test_eval_raises_file_not_found(tmp_path: Path) -> None:
    runner = DockerSandboxRunner()
    with pytest.raises(FileNotFoundError):
        runner.run("x = 1\n", tmp_path / "nonexistent_test_eval.py")
