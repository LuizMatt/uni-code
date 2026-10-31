import json
import os
import secrets
import subprocess
import sys
from pathlib import Path
from typing import Any


def main() -> int:
    timeout_sec = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    token = secrets.token_hex(8)
    report_path = Path(f"/tmp/report-{token}.json")

    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "PYTHONPATH": "/workspace",
        "PYTHONDONTWRITEBYTECODE": "1",
        "HOME": "/tmp",
    }

    cmd = [
        sys.executable,
        "-I",
        "-m",
        "pytest",
        "/workspace/test_eval.py",
        "-q",
        "--tb=short",
        "--no-header",
        "-p",
        "no:cacheprovider",
        "--json-report",
        f"--json-report-file={report_path}",
    ]

    timed_out = False
    exit_code = -1
    stdout_text = ""
    stderr_text = ""

    try:
        proc = subprocess.run(
            cmd,
            cwd="/tmp",
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        exit_code = proc.returncode
        stdout_text = proc.stdout
        stderr_text = proc.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = -9
        stdout_text = (
            exc.stdout.decode("utf-8", errors="replace")
            if isinstance(exc.stdout, bytes)
            else (exc.stdout or "")
        )
        stderr_text = (
            exc.stderr.decode("utf-8", errors="replace")
            if isinstance(exc.stderr, bytes)
            else (exc.stderr or "")
        )

    report_data: dict[str, Any] | None = None
    if not timed_out and report_path.exists():
        try:
            raw = json.loads(report_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                report_data = raw
        except Exception:
            report_data = None

    envelope = {
        "timed_out": timed_out,
        "exit_code": exit_code,
        "stdout": stdout_text,
        "stderr": stderr_text,
        "report": report_data,
    }
    sys.stdout.write(json.dumps(envelope))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
