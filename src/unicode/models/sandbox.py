from dataclasses import dataclass
from typing import Literal

SandboxOutcome = Literal["passed", "failed", "timeout", "oom", "error"]


@dataclass(frozen=True, slots=True)
class SandboxResult:
    outcome: SandboxOutcome
    tests_total: int
    tests_passed: int
    first_failed_test: str | None = None
    error_category: str | None = None
    diagnostic_output: str = ""
