from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal


@dataclass(frozen=True, slots=True)
class UnitDefinition:
    code: str
    title: str
    opens_at: datetime | None = None
    closes_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class QuestionDefinition:
    slug: str
    unit_code: str
    title: str
    active: bool = True
    timeout_seconds: int = 3
    dir_path: Path = field(default_factory=Path)


@dataclass(frozen=True, slots=True)
class QuestionIssue:
    path: Path | str
    message: str
    kind: Literal["error", "warning"] = "error"


@dataclass(frozen=True, slots=True)
class ScanResult:
    units: list[UnitDefinition] = field(default_factory=list)
    questions: list[QuestionDefinition] = field(default_factory=list)
    issues: list[QuestionIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[QuestionIssue]:
        return [i for i in self.issues if i.kind == "error"]

    @property
    def warnings(self) -> list[QuestionIssue]:
        return [i for i in self.issues if i.kind == "warning"]

    @property
    def has_errors(self) -> bool:
        return any(i.kind == "error" for i in self.issues)


@dataclass(frozen=True, slots=True)
class SyncReport:
    units_created: int = 0
    units_updated: int = 0
    questions_created: int = 0
    questions_updated: int = 0
    questions_deactivated: int = 0
    issues: list[QuestionIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[QuestionIssue]:
        return [i for i in self.issues if i.kind == "error"]

    @property
    def warnings(self) -> list[QuestionIssue]:
        return [i for i in self.issues if i.kind == "warning"]

    @property
    def has_errors(self) -> bool:
        return any(i.kind == "error" for i in self.issues)
