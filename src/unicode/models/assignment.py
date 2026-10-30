from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Literal

AssignmentState = Literal["pending", "passed", "exhausted", "replaced"]


@dataclass(frozen=True, slots=True)
class Assignment:
    id: int
    student_registration: str
    unit_id: int
    unit_code: str
    question_id: int
    question_slug: str
    round: int
    state: AssignmentState
    points: Decimal
    created_at: datetime


@dataclass(frozen=True, slots=True)
class DrawResult:
    student_registration: str
    unit_code: str
    assignments: list[Assignment] = field(default_factory=list)
    created: bool = False


@dataclass(frozen=True, slots=True)
class ResetResult:
    student_registration: str
    unit_code: str
    new_round: int
    replaced_assignments: list[Assignment] = field(default_factory=list)
    new_assignments: list[Assignment] = field(default_factory=list)
    reused_questions: bool = False
