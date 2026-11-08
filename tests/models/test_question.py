from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from pathlib import Path

import pytest

from unicode.models.question import (
    QuestionDefinition,
    QuestionIssue,
    ScanResult,
    SyncReport,
    UnitDefinition,
)


def test_unit_definition_immutability() -> None:
    now = datetime.now(UTC)
    u = UnitDefinition(code="unit-01", title="U1", opens_at=now, closes_at=None)
    assert u.code == "unit-01"
    with pytest.raises(FrozenInstanceError):
        u.title = "New"  # type: ignore[misc]


def test_question_definition_immutability_and_defaults() -> None:
    q = QuestionDefinition(slug="soma", unit_code="unit-01", title="Soma")
    assert q.slug == "soma"
    assert q.active is True
    assert q.timeout_seconds == 3
    assert q.dir_path == Path()
    with pytest.raises(FrozenInstanceError):
        q.active = False  # type: ignore[misc]


def test_scan_result_helpers() -> None:
    res = ScanResult(
        units=[],
        questions=[],
        issues=[
            QuestionIssue(path=Path("u1"), message="aviso", kind="warning"),
            QuestionIssue(path=Path("u2"), message="erro", kind="error"),
        ],
    )
    assert res.has_errors is True
    assert len(res.errors) == 1
    assert len(res.warnings) == 1


def test_sync_report_helpers() -> None:
    report = SyncReport(
        units_created=1,
        issues=[
            QuestionIssue(path=Path("u1"), message="aviso", kind="warning"),
            QuestionIssue(path=Path("u2"), message="erro", kind="error"),
        ],
    )
    assert report.has_errors is True
    assert len(report.errors) == 1
    assert len(report.warnings) == 1
