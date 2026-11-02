from dataclasses import dataclass
from datetime import datetime

from unicode.models.assignment import AssignmentState
from unicode.models.attempt import AttemptStatus
from unicode.models.student import Student


@dataclass(frozen=True, slots=True)
class OverviewStats:
    """High-level metrics displayed on the professor overview dashboard."""

    total_students: int
    total_units: int
    active_questions: int
    submissions_today: int
    approved_assignments: int
    decided_assignments: int
    approval_rate: float


@dataclass(frozen=True, slots=True)
class UnitSummary:
    """Summary of a unit for the overview table."""

    code: str
    title: str
    active_questions: int
    students_started: int
    average_points: float


@dataclass(frozen=True, slots=True)
class StudentUnitGrade:
    """Single row of a student's grade in a specific unit (used for CSV export)."""

    registration: str
    email: str
    name: str | None
    class_group: str | None
    unit_code: str
    points: float


@dataclass(frozen=True, slots=True)
class StudentGradesSummary:
    """Aggregated grades across all units for a student."""

    registration: str
    email: str
    name: str | None
    class_group: str | None
    grades_by_unit: dict[str, float]
    total_points: float


@dataclass(frozen=True, slots=True)
class AttemptDetail:
    """Full attempt record including submitted code snapshot for the professor panel."""

    id: int
    number: int
    status: AttemptStatus
    tests_total: int | None
    tests_passed: int | None
    output: str | None
    code: str
    started_at: datetime
    finished_at: datetime | None


@dataclass(frozen=True, slots=True)
class AssignmentHistoryItem:
    """Assignment record (active or replaced) with all its attempts."""

    id: int
    unit_code: str
    question_slug: str
    question_title: str
    round: int
    state: AssignmentState
    points: float
    created_at: datetime
    attempts: tuple[AttemptDetail, ...]


@dataclass(frozen=True, slots=True)
class StudentDetailReport:
    """Detailed history of a single student across all units and rounds."""

    student: Student
    grades_by_unit: dict[str, float]
    total_points: float
    assignments: tuple[AssignmentHistoryItem, ...]


@dataclass(frozen=True, slots=True)
class QuestionRateStat:
    """Performance and hit-rate metrics for a single question inside a unit."""

    slug: str
    title: str
    active: bool
    assigned_count: int
    passed_count: int
    exhausted_count: int
    pending_count: int
    pass_rate: float
    avg_attempts: float


@dataclass(frozen=True, slots=True)
class UnitDetailReport:
    """Detailed question metrics for a unit."""

    code: str
    title: str
    questions: tuple[QuestionRateStat, ...]
