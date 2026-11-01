from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Session:
    student_registration: str
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class IssuedSession:
    token: str
    session: Session
