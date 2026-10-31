import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from unicode.config import Settings, get_settings
from unicode.models.sandbox import SandboxResult

_ERROR_TYPE_RE = re.compile(
    r"\b(SyntaxError|IndentationError|TabError|ImportError|ModuleNotFoundError|"
    r"NameError|TypeError|MemoryError|RecursionError|OSError|PermissionError)\b"
)


class SandboxRunner(Protocol):
    """Protocol for isolated test execution engines."""

    def run(self, code: str, test_eval_path: Path) -> SandboxResult: ...


def _build_docker_run_cmd(
    *,
    container_name: str,
    workspace_dir: Path,
    settings: Settings,
) -> list[str]:
    resolved_ws = workspace_dir.resolve()
    return [
        "docker",
        "run",
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
        str(settings.sandbox_pids_limit),
        "--memory",
        f"{settings.sandbox_memory_mb}m",
        "--memory-swap",
        f"{settings.sandbox_memory_mb}m",
        "--cpus",
        str(settings.sandbox_cpus),
        "--user",
        "65534:65534",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=16m,mode=1777",
        "-v",
        f"{resolved_ws}:/workspace:ro",
        settings.sandbox_image,
        str(settings.sandbox_timeout_seconds),
    ]


def _extract_error_category(text: str, default: str = "ExecutionError") -> str:
    match = _ERROR_TYPE_RE.search(text)
    if match:
        return match.group(1)
    return default


def _parse_container_execution(
    *,
    returncode: int,
    stdout: str,
    stderr: str,
) -> SandboxResult:
    if returncode == 137:
        diag = f"Container finalizado por limite de memória (exit 137).\n{stderr}".strip()
        return SandboxResult(
            outcome="oom",
            tests_total=0,
            tests_passed=0,
            error_category="MemoryError",
            diagnostic_output=diag,
        )

    try:
        envelope = json.loads(stdout) if stdout.strip() else None
    except json.JSONDecodeError:
        envelope = None

    if not isinstance(envelope, dict):
        combined = f"returncode={returncode}\nstdout={stdout}\nstderr={stderr}".strip()
        if "MemoryError" in combined:
            return SandboxResult(
                outcome="oom",
                tests_total=0,
                tests_passed=0,
                error_category="MemoryError",
                diagnostic_output=combined,
            )
        return SandboxResult(
            outcome="error",
            tests_total=0,
            tests_passed=0,
            error_category="SandboxError",
            diagnostic_output=combined,
        )

    if bool(envelope.get("timed_out")):
        diag = (
            f"Tempo limite excedido.\n{envelope.get('stdout', '')}\n{envelope.get('stderr', '')}"
        ).strip()
        return SandboxResult(
            outcome="timeout",
            tests_total=0,
            tests_passed=0,
            error_category="TimeoutError",
            diagnostic_output=diag,
        )

    inner_exit = int(envelope.get("exit_code", -1))
    inner_stdout = str(envelope.get("stdout", ""))
    inner_stderr = str(envelope.get("stderr", ""))
    combined_out = f"{inner_stdout}\n{inner_stderr}".strip()

    if inner_exit in (-9, 137) or "MemoryError" in combined_out:
        return SandboxResult(
            outcome="oom",
            tests_total=0,
            tests_passed=0,
            error_category="MemoryError",
            diagnostic_output=combined_out or "Estouro de memória detectado na sandbox.",
        )

    report = envelope.get("report")
    if not isinstance(report, dict):
        category = _extract_error_category(combined_out, default="ExecutionError")
        return SandboxResult(
            outcome="error",
            tests_total=0,
            tests_passed=0,
            error_category=category,
            diagnostic_output=combined_out or f"Falha sem relatório JSON (exit={inner_exit}).",
        )

    collectors: list[dict[str, Any]] = [
        c for c in (report.get("collectors") or []) if isinstance(c, dict)
    ]
    failed_collectors = [c for c in collectors if c.get("outcome") == "failed"]
    if failed_collectors:
        longreprs = "\n".join(str(c.get("longrepr", "")) for c in failed_collectors).strip()
        diag = f"{longreprs}\n{combined_out}".strip()
        category = _extract_error_category(diag, default="CollectionError")
        if category == "MemoryError":
            return SandboxResult(
                outcome="oom",
                tests_total=0,
                tests_passed=0,
                error_category="MemoryError",
                diagnostic_output=diag,
            )
        return SandboxResult(
            outcome="error",
            tests_total=0,
            tests_passed=0,
            error_category=category,
            diagnostic_output=diag,
        )

    tests_list: list[dict[str, Any]] = [
        t for t in (report.get("tests") or []) if isinstance(t, dict)
    ]
    tests_total = len(tests_list)
    if tests_total == 0:
        category = _extract_error_category(combined_out, default="NoTestsCollected")
        return SandboxResult(
            outcome="error",
            tests_total=0,
            tests_passed=0,
            error_category=category,
            diagnostic_output=combined_out or "Nenhum teste coletado.",
        )

    tests_passed = sum(1 for t in tests_list if t.get("outcome") == "passed")
    first_failed_test: str | None = None
    failure_details: list[str] = []

    for t in tests_list:
        if t.get("outcome") != "passed":
            nodeid = str(t.get("nodeid", ""))
            test_name = nodeid.split("::")[-1] if "::" in nodeid else nodeid
            if first_failed_test is None and test_name:
                first_failed_test = test_name
            call_info = t.get("call")
            if isinstance(call_info, dict) and call_info.get("longrepr"):
                failure_details.append(f"[{test_name}]\n{call_info['longrepr']}")

    diag_parts = [f"passed={tests_passed}/{tests_total}"]
    if failure_details:
        diag_parts.extend(failure_details)
    if combined_out:
        diag_parts.append(combined_out)
    diagnostic_output = "\n\n".join(diag_parts)

    if tests_passed == tests_total and inner_exit == 0:
        return SandboxResult(
            outcome="passed",
            tests_total=tests_total,
            tests_passed=tests_passed,
            diagnostic_output=diagnostic_output,
        )

    return SandboxResult(
        outcome="failed",
        tests_total=tests_total,
        tests_passed=tests_passed,
        first_failed_test=first_failed_test,
        diagnostic_output=diagnostic_output,
    )


def run_in_sandbox(
    code: str,
    test_eval_path: Path,
    *,
    settings: Settings | None = None,
) -> SandboxResult:
    """Run student code against `test_eval_path` inside an ephemeral hardened container."""
    if not test_eval_path.exists() or not test_eval_path.is_file():
        raise FileNotFoundError(f"arquivo de testes não encontrado: {test_eval_path}")

    cfg = settings or get_settings()
    container_name = f"unicode-sbx-{uuid4().hex}"

    with tempfile.TemporaryDirectory(prefix="unicode-sbx-") as tmp_str:
        tmp_dir = Path(tmp_str)
        os.chmod(tmp_dir, 0o755)

        solution_file = tmp_dir / "solution.py"
        solution_file.write_text(code, encoding="utf-8")
        os.chmod(solution_file, 0o644)

        eval_dest = tmp_dir / "test_eval.py"
        shutil.copyfile(test_eval_path, eval_dest)
        os.chmod(eval_dest, 0o644)

        cmd = _build_docker_run_cmd(
            container_name=container_name,
            workspace_dir=tmp_dir,
            settings=cfg,
        )
        host_timeout = cfg.sandbox_timeout_seconds + 3

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=host_timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return SandboxResult(
                outcome="timeout",
                tests_total=0,
                tests_passed=0,
                error_category="TimeoutError",
                diagnostic_output=(
                    f"Execução excedeu o tempo máximo de {cfg.sandbox_timeout_seconds}s."
                ),
            )
        finally:
            try:
                subprocess.run(
                    ["docker", "rm", "-f", container_name],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=10,
                    check=False,
                )
            except Exception:
                pass

    return _parse_container_execution(
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )


class DockerSandboxRunner:
    """Default Docker-based sandbox runner."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings

    def run(self, code: str, test_eval_path: Path) -> SandboxResult:
        return run_in_sandbox(code, test_eval_path, settings=self._settings)
