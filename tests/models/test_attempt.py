from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from unicode.models import (
    Assignment,
    Attempt,
    ReservedAttempt,
    SandboxResult,
    StudentFeedback,
    SubmissionResult,
)


def test_sandbox_result_immutability_and_defaults() -> None:
    res = SandboxResult(outcome="passed", tests_total=3, tests_passed=3)
    assert res.outcome == "passed"
    assert res.first_failed_test is None
    assert res.error_category is None
    assert res.diagnostic_output == ""
    with pytest.raises(FrozenInstanceError):
        res.tests_passed = 0  # type: ignore[misc]


def test_attempt_and_submission_result_models() -> None:
    now = datetime.now(UTC)
    assignment = Assignment(
        id=10,
        student_registration="2026001",
        unit_id=1,
        unit_code="unit-01",
        question_id=100,
        question_slug="soma-dois-numeros",
        round=1,
        state="passed",
        points=Decimal("0.5"),
        created_at=now,
    )
    attempt = Attempt(
        id=50,
        assignment_id=10,
        number=1,
        status="passed",
        code="def soma(a, b):\n    return a + b\n",
        started_at=now,
        tests_total=3,
        tests_passed=3,
        output="3 passed",
        finished_at=now,
    )
    reserved = ReservedAttempt(attempt=attempt, assignment=assignment)
    assert reserved.attempt.id == 50
    assert reserved.assignment.question_slug == "soma-dois-numeros"

    feedback = StudentFeedback(
        status="passed",
        tests_total=3,
        tests_passed=3,
        attempt_number=1,
        attempts_remaining=0,
        assignment_state="passed",
        points=Decimal("0.5"),
    )
    sub_result = SubmissionResult(
        attempt=attempt,
        assignment=assignment,
        feedback=feedback,
    )
    assert sub_result.feedback.points == Decimal("0.5")
    assert sub_result.feedback.first_failed_test is None
    with pytest.raises(FrozenInstanceError):
        sub_result.feedback.status = "failed"  # type: ignore[misc]

