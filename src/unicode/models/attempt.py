from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from unicode.models.assignment import Assignment, AssignmentState

AttemptStatus = Literal["running", "passed", "failed", "error"]
FeedbackStatus = Literal["passed", "failed", "error"]


@dataclass(frozen=True, slots=True)
class Attempt:
    id: int
    assignment_id: int
    number: int
    status: AttemptStatus
    code: str
    started_at: datetime
    tests_total: int | None = None
    tests_passed: int | None = None
    output: str | None = None
    finished_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ReservedAttempt:
    attempt: Attempt
    assignment: Assignment


@dataclass(frozen=True, slots=True)
class StudentFeedback:
    status: FeedbackStatus
    tests_total: int
    tests_passed: int
    attempt_number: int
    attempts_remaining: int
    assignment_state: AssignmentState
    points: Decimal
    first_failed_test: str | None = None
    error_category: str | None = None


@dataclass(frozen=True, slots=True)
class SubmissionResult:
    attempt: Attempt
    assignment: Assignment
    feedback: StudentFeedback
