import subprocess

import pytest

from tests.support import ROOT
from unicode.config import Settings
from unicode.sandbox.runner import DockerSandboxRunner


@pytest.fixture(scope="module")
def sandbox_image() -> str:
    image_tag = "unicode-sandbox:test"
    try:
        info = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
        if info.returncode != 0:
            pytest.skip("Docker daemon indisponível para testes de integração da sandbox")
    except (FileNotFoundError, subprocess.SubprocessError):
        pytest.skip("CLI docker indisponível para testes de integração da sandbox")

    build = subprocess.run(
        ["docker", "build", "-t", image_tag, str(ROOT / "docker" / "sandbox")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    if build.returncode != 0:
        pytest.skip(f"Não foi possível construir a imagem da sandbox: {build.stderr}")
    return image_tag


@pytest.mark.docker
def test_sandbox_integration_all_scenarios(sandbox_image: str) -> None:
    settings = Settings(
        sandbox_image=sandbox_image,
        sandbox_timeout_seconds=2,
        sandbox_memory_mb=128,
    )
    runner = DockerSandboxRunner(settings=settings)
    test_eval = ROOT / "questions" / "unit-01" / "soma-dois-numeros" / "test_eval.py"

    # 1. Correct solution
    ok_res = runner.run("def soma(a: int, b: int) -> int:\n    return a + b\n", test_eval)
    assert ok_res.outcome == "passed"
    assert ok_res.tests_total == 3
    assert ok_res.tests_passed == 3

    # 2. Wrong solution
    wrong_res = runner.run("def soma(a: int, b: int) -> int:\n    return a - b\n", test_eval)
    assert wrong_res.outcome == "failed"
    assert wrong_res.tests_total == 3
    assert wrong_res.tests_passed < 3
    assert wrong_res.first_failed_test is not None

    # 3. Infinite loop (timeout)
    loop_res = runner.run(
        "def soma(a: int, b: int) -> int:\n    while True:\n        pass\n",
        test_eval,
    )
    assert loop_res.outcome == "timeout"
    assert loop_res.error_category == "TimeoutError"

    # 4. Memory exhaustion
    oom_res = runner.run(
        "x = bytearray(300 * 1024 * 1024)\ndef soma(a: int, b: int) -> int:\n    return a + b\n",
        test_eval,
    )
    assert oom_res.outcome in ("oom", "error")
    assert oom_res.tests_passed == 0

    # 5. Network access attempt + read-only root/workspace write attempt
    sec_code = (
        "import socket\n"
        "from pathlib import Path\n"
        "def soma(a: int, b: int) -> int:\n"
        "    try:\n"
        "        Path('/workspace/hack.py').write_text('x')\n"
        "        return 0\n"
        "    except OSError:\n"
        "        pass\n"
        "    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
        "    s.connect(('8.8.8.8', 53))\n"
        "    return a + b\n"
    )
    sec_res = runner.run(sec_code, test_eval)
    assert sec_res.outcome == "failed"
    assert sec_res.tests_passed == 0
