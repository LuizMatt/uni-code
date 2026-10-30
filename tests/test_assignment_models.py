from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from unicode.models.assignment import (
    Assignment,
    DrawResult,
    ResetResult,
)


def test_assignment_immutability() -> None:
    now = datetime.now(UTC)
    a = Assignment(
        id=1,
        student_registration="2026001",
        unit_id=10,
        unit_code="unit-01",
        question_id=100,
        question_slug="soma-dois-numeros",
        round=1,
        state="pending",
        points=Decimal("0.0"),
        created_at=now,
    )
    assert a.student_registration == "2026001"
    assert a.question_slug == "soma-dois-numeros"
    assert a.points == Decimal("0.0")
    with pytest.raises(FrozenInstanceError):
        a.state = "passed"  # type: ignore[misc]


def test_draw_and_reset_result_defaults() -> None:
    draw = DrawResult(student_registration="2026001", unit_code="unit-01")
    assert draw.assignments == []
    assert draw.created is False

    reset = ResetResult(
        student_registration="2026001",
        unit_code="unit-01",
        new_round=2,
    )
    assert reset.replaced_assignments == []
    assert reset.new_assignments == []
    assert reset.reused_questions is False
