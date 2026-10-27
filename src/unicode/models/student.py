from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass(frozen=True, slots=True)
class StudentRow:
    line_number: int
    registration: str
    email: str
    name: str | None = None
    class_group: str | None = None


@dataclass(frozen=True, slots=True)
class RowIssue:
    line_number: int
    message: str
    kind: Literal["error", "warning"] = "error"


@dataclass(frozen=True, slots=True)
class ParseResult:
    valid_rows: list[StudentRow] = field(default_factory=list)
    issues: list[RowIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[RowIssue]:
        return [i for i in self.issues if i.kind == "error"]

    @property
    def warnings(self) -> list[RowIssue]:
        return [i for i in self.issues if i.kind == "warning"]

    @property
    def has_errors(self) -> bool:
        return any(i.kind == "error" for i in self.issues)


@dataclass(frozen=True, slots=True)
class ImportReport:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    issues: list[RowIssue] = field(default_factory=list)

    @property
    def total_processed(self) -> int:
        return self.created + self.updated + self.unchanged

    @property
    def errors(self) -> list[RowIssue]:
        return [i for i in self.issues if i.kind == "error"]

    @property
    def warnings(self) -> list[RowIssue]:
        return [i for i in self.issues if i.kind == "warning"]

    @property
    def has_errors(self) -> bool:
        return any(i.kind == "error" for i in self.issues)


@dataclass(frozen=True, slots=True)
class Student:
    registration: str
    email: str
    name: str | None
    class_group: str | None
    created_at: datetime
